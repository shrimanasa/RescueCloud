# RescueCloud — AWS (EKS) Production Deployment Checklist

This is the actual sequence required before `kubectl apply -k k8s/` does
anything useful on AWS. The manifests in `k8s/` are necessary but not
sufficient — each depends on cluster-level setup listed here. Skipping a
step means the corresponding manifest silently fails to reconcile (ESO
won't sync, cert-manager won't issue, Ingress won't get an address).

Nothing in this checklist can be run from a sandboxed assistant — it
requires your AWS account, billing, and credentials.

## 0. Prerequisites
- An AWS account with billing enabled
- A registered domain (Route 53, or another registrar with Route 53 as the
  DNS host) — needed before step 7, not before
- `awscli`, `eksctl`, `kubectl`, `helm` installed locally

## 1. Create the EKS cluster with OIDC enabled
```bash
eksctl create cluster \
  --name rescuecloud-prod \
  --region us-east-1 \
  --nodegroup-name standard-workers \
  --node-type t3.medium \
  --nodes 3 \
  --nodes-min 2 \
  --nodes-max 5 \
  --managed

eksctl utils associate-iam-oidc-provider \
  --cluster rescuecloud-prod --approve
```
IRSA (used by External Secrets in step 4) does not work without the OIDC
provider association — this is the step most commonly skipped.

## 2. Install the ingress controller
```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace
```
This provisions an AWS Network Load Balancer. Get its hostname:
```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```
You'll point DNS at this in step 7.

## 3. Install cert-manager
```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  -n cert-manager --create-namespace --set installCRDs=true
```
Then apply `k8s/09-cert-issuer.yaml` (defines `letsencrypt-prod`,
`letsencrypt-staging`, and a self-signed issuer for local/air-gapped use).
Use `letsencrypt-staging` first — Let's Encrypt rate-limits the production
issuer aggressively, and a failed staging attempt costs nothing.

## 4. Create the IAM role for External Secrets (IRSA)
Create a policy scoped to only the four secret paths this app reads —
not full `SecretsManager:*`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:rescuecloud/database-*",
        "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:rescuecloud/minio-*",
        "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:rescuecloud/auth-*",
        "arn:aws:secretsmanager:us-east-1:<ACCOUNT_ID>:secret:rescuecloud/blockchain-*"
      ]
    }
  ]
}
```

```bash
aws iam create-policy \
  --policy-name RescueCloudESOReadOnly \
  --policy-document file://rescuecloud-eso-policy.json

eksctl create iamserviceaccount \
  --name rescuecloud-eso-sa \
  --namespace rescuecloud \
  --cluster rescuecloud-prod \
  --attach-policy-arn arn:aws:iam::<ACCOUNT_ID>:policy/RescueCloudESOReadOnly \
  --approve
```
`eksctl create iamserviceaccount` creates both the IAM role (trusted to the
OIDC provider) and the matching Kubernetes ServiceAccount in one step —
you don't need to hand-write the trust policy. This replaces the manually
annotated ServiceAccount at the top of `k8s/01-external-secrets.yaml`; once
this command has run, delete that ServiceAccount block from the manifest so
kustomize doesn't fight eksctl's version.

## 5. Install External Secrets Operator
```bash
helm repo add external-secrets https://charts.external-secrets.io
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace
```

## 6. Create the actual secrets in AWS Secrets Manager
ESO only *reads* secrets — nothing creates them for you. Generate real
values (not the placeholders in this repo) and store them as JSON blobs:
```bash
aws secretsmanager create-secret --name rescuecloud/database \
  --secret-string '{"username":"rescueadmin","password":"<GENERATE>","database_name":"rescuecloud_ehr"}'
aws secretsmanager create-secret --name rescuecloud/auth \
  --secret-string '{"jwt_secret_key":"<GENERATE 32+ CHAR RANDOM>","admin_username":"<REAL EMAIL>","admin_password":"<GENERATE>"}'
aws secretsmanager create-secret --name rescuecloud/minio \
  --secret-string '{"root_user":"<GENERATE>","root_password":"<GENERATE>"}'
aws secretsmanager create-secret --name rescuecloud/blockchain \
  --secret-string '{"rpc_url":"<YOUR RPC URL>","contract_address":"<DEPLOYED CONTRACT ADDR>"}'
```

## 7. Point DNS at the load balancer
In Route 53, create CNAME records for your two hosts (`ehr.<yourdomain>`,
`api.<yourdomain>`) pointing at the NLB hostname from step 2. Update
`k8s/09-ingress.yaml` to replace `ehr.rescuecloud.io` / `api.rescuecloud.io`
with your real domain before applying — the placeholder domain in this repo
resolves to nothing.

## 8. Install CloudNativePG operator (for the HA Postgres cluster)
```bash
kubectl apply --server-side -f \
  https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.22/releases/cnpg-1.22.0.yaml
```

## 9. Apply everything
```bash
kubectl apply -k k8s/
```

## 10. Verify
```bash
kubectl get certificate -n rescuecloud        # should show READY=True within a few minutes
kubectl get externalsecret -n rescuecloud     # SecretSynced condition should be True
kubectl get cluster.postgresql.cnpg.io -n rescuecloud  # 3/3 instances ready
curl -I https://ehr.<yourdomain>              # real TLS cert, no browser warning
```

## Cost note
EKS control plane (~$0.10/hr) + 2-3 t3.medium nodes + NLB is roughly
$150-250/month minimum, before RDS/storage. There is no free-tier way to
run this exact HA setup continuously — budget for it before step 1, or use
the local/self-contained option instead for demos.


---

## Troubleshooting

**eksctl create cluster times out:** Check IAM permissions (eks:*, ec2:*, iam:PassRole).

**ESO SecretStore reports InvalidCredentials:** Confirm IRSA annotation matches the IAM role ARN. Check `kubectl logs -n external-secrets deploy/external-secrets`.

**cert-manager CertificateRequest stuck in Pending:** Verify Let's Encrypt HTTP-01 challenge can reach port 80. Run `kubectl describe certificaterequest -n rescuecloud`.

**CloudNativePG stays in Setting Up Primary:** Check `kubectl logs -n rescuecloud cluster-rescuecloud-1` for WAL archive errors.


---

## Cost Optimisation

| Change | Saving |
|---|---|
| t3.medium instead of t3.large | ~$30/month |
| CloudNativePG 1 replica for dev | ~$40/month |
| S3 Intelligent-Tiering for WAL | ~$5-15/month |

**Production:** do NOT apply these. HA Postgres and t3.large are sized for HIPAA availability.
