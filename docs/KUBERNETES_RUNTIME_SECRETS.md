# Kubernetes runtime credentials

Application credentials must never be stored in Git, Docker images, build
artifacts, Jenkins logs, or generated Kubernetes YAML files.

## Runtime contract

Both application namespaces contain an independently managed Opaque Secret
named `vyb-runtime-config`. The Secret is mounted read-only at:

`/var/run/secrets/vyb`

Required keys:

| Secret key | Mounted path | Purpose |
| --- | --- | --- |
| `vibr_config.json` | `/var/run/secrets/vyb/vibr_config.json` | AWS, OpenAI, Google and profile runtime configuration |
| `vibr_registration_config.json` | `/var/run/secrets/vyb/vibr_registration_config.json` | Cognito, SES and JWT runtime configuration |
| `Config.json` | `/var/run/secrets/vyb/Config.json` | Legacy cloud-provider runtime configuration |
| `firebase-admin.json` | `/var/run/secrets/vyb/firebase-admin.json` | Firebase Admin service account |

Development and production use separate Secret objects and should use separate
provider credentials. Kubernetes manifests contain only the Secret name and
mount path.

## Provision or rotate

Prepare the four files outside every Git worktree. Do not generate a Secret
manifest on disk.

```powershell
$env:KUBECONFIG=(Resolve-Path '.\.kubeconfig-vyb').Path

kubectl create secret generic vyb-runtime-config `
  --namespace vyb-development `
  --from-file=vibr_config.json='C:\secure\dev\vibr_config.json' `
  --from-file=vibr_registration_config.json='C:\secure\dev\vibr_registration_config.json' `
  --from-file=Config.json='C:\secure\dev\Config.json' `
  --from-file=firebase-admin.json='C:\secure\dev\firebase-admin.json' `
  --dry-run=client -o yaml |
kubectl apply -f -

kubectl rollout restart deployment/vyb-api -n vyb-development
kubectl rollout status deployment/vyb-api -n vyb-development --timeout=20m
```

Repeat with production-only source files and the `vyb-production` namespace.
Never reuse development credentials in production after the initial migration.

## Verification without disclosure

```powershell
kubectl get secret vyb-runtime-config -n vyb-development `
  -o jsonpath='{.metadata.name}'
kubectl exec -n vyb-development deploy/vyb-api -- `
  sh -c 'test -r /var/run/secrets/vyb/vibr_config.json &&
         test -r /var/run/secrets/vyb/vibr_registration_config.json &&
         test -r /var/run/secrets/vyb/Config.json &&
         test -r /var/run/secrets/vyb/firebase-admin.json'
```

Do not use `kubectl get secret -o yaml`, decode Secret data, or paste provider
credentials into tickets, chat, documentation, or shell history.

## Incident cleanup

Credentials previously committed to Git or copied into an image are
compromised even after removal from the current branch.

1. Rotate AWS, Firebase, OpenAI, Google, Cognito and JWT credentials.
2. Update the namespace Secrets and restart the affected deployment.
3. Review provider access logs for unauthorized activity.
4. Coordinate a Git-history rewrite across every branch and tag.
5. Require all contributors to re-clone after the force-push.
6. Remove affected historical images from Harbor after replacement images are
   verified and rollback policy permits deletion.

The Jenkins pipelines run `scripts/scan-secrets.py` and reject tracked
credential files or high-confidence key patterns.
