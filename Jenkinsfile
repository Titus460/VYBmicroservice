properties([
  disableConcurrentBuilds(),
  buildDiscarder(logRotator(numToKeepStr: '20'))
])

def agentYaml = '''
apiVersion: v1
kind: Pod
spec:
  serviceAccountName: jenkins-deployer
  containers:
    - name: python
      image: python:3.10-slim
      command: ["sh", "-c", "cat"]
      tty: true
      resources:
        requests:
          cpu: 100m
          memory: 128Mi
        limits:
          cpu: 500m
          memory: 512Mi
    - name: kaniko
      image: gcr.io/kaniko-project/executor:v1.23.2-debug
      command: ["/busybox/cat"]
      tty: true
      env:
        - name: SSL_CERT_FILE
          value: /kaniko/ssl/certs/additional-ca-cert-bundle.crt
      resources:
        requests:
          cpu: 500m
          memory: 1Gi
        limits:
          cpu: "1"
          memory: 6Gi
      volumeMounts:
        - name: registry-config
          mountPath: /kaniko/.docker
        - name: harbor-ca
          mountPath: /kaniko/ssl/certs/additional-ca-cert-bundle.crt
          subPath: ca.crt
    - name: kubectl
      image: alpine/k8s:1.35.0
      command: ["sh", "-c", "cat"]
      tty: true
      resources:
        requests:
          cpu: 50m
          memory: 64Mi
        limits:
          cpu: 250m
          memory: 256Mi
  volumes:
    - name: registry-config
      secret:
        secretName: registry-vyb
        items:
          - key: .dockerconfigjson
            path: config.json
    - name: harbor-ca
      secret:
        secretName: harbor-registry-ca
        items:
          - key: ca.crt
            path: ca.crt
'''

podTemplate(yaml: agentYaml) {
  node(POD_LABEL) {
    def pipelineError = null
    try {
      timestamps {
      timeout(time: 45, unit: 'MINUTES') {
        withEnv([
          'REGISTRY=harbor.harbor.svc.cluster.local',
          'IMAGE_NAME=vyb/vyb-api',
          'DEPLOYMENT=vyb-api',
          'NAMESPACE=vyb-development'
        ]) {
          stage('Checkout') {
            def checkoutInfo = checkout scm
            env.GIT_COMMIT = checkoutInfo.GIT_COMMIT ?: sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
            sh 'git ls-files -z > .tracked-files'
            echo "Checked out commit ${env.GIT_COMMIT}"
          }

          stage('Validate source') {
            container('python') {
              sh '''
                set -eu
                python scripts/scan-secrets.py
                python -m compileall -q app.py App Model
                python - <<'PY'
from pathlib import Path

requirements = Path("requirements.txt").read_bytes()
if requirements.startswith(bytes([239, 187, 191])):
    raise SystemExit("requirements.txt must not contain a UTF-8 BOM")
PY
              '''
            }
          }

          stage('Install pinned quality tools') {
            container('python') {
              sh '''
                set -eu
                python -m pip install --disable-pip-version-check --no-cache-dir \
                  -r requirements-ci.txt
                mkdir -p reports
              '''
            }
          }

          stage('Static analysis and security gates') {
            container('python') {
              sh '''
                set +e
                rm -f .quality-gate-failed

                ruff check . --output-format=junit --output-file=reports/ruff.xml
                ruff_status=$?
                if [ "$ruff_status" -ne 0 ]; then
                  echo "ERROR: Ruff correctness gate failed"
                  touch .quality-gate-failed
                fi

                bandit -r app.py App Model \
                  --skip B413 \
                  --severity-level high \
                  --confidence-level high \
                  --format screen
                bandit_status=$?
                if [ "$bandit_status" -ne 0 ]; then
                  echo "ERROR: Bandit high-severity/high-confidence gate failed"
                  touch .quality-gate-failed
                fi

                bandit -r app.py App Model --skip B413 --format json \
                  --output reports/bandit.json || true
              '''
            }
          }

          stage('Unit tests and routing coverage') {
            container('python') {
              sh '''
                set +e
                pytest \
                  --junitxml=reports/pytest.xml \
                  --cov=Model.db_routing \
                  --cov-report=term-missing \
                  --cov-report=xml:reports/coverage.xml \
                  --cov-fail-under=85
                test_status=$?
                if [ "$test_status" -ne 0 ]; then
                  echo "ERROR: pytest or routing coverage gate failed"
                  touch .quality-gate-failed
                fi
              '''
            }
          }

          stage('Dependency vulnerability inventory') {
            container('python') {
              sh '''
                set +e
                pip-audit \
                  --no-deps \
                  --disable-pip \
                  --requirement requirements.txt \
                  --progress-spinner off \
                  --format json \
                  --output reports/pip-audit.json
                audit_status=$?
                if [ "$audit_status" -ne 0 ]; then
                  echo "WARNING: known dependency vulnerabilities were found."
                  echo "The JSON report is archived; this becomes blocking after dependency remediation."
                fi
                exit 0
              '''
            }
          }

          stage('Publish quality reports') {
            junit testResults: 'reports/pytest.xml,reports/ruff.xml', allowEmptyResults: false
            archiveArtifacts artifacts: 'reports/**', fingerprint: true
          }

          stage('Enforce quality gate') {
            container('python') {
              sh '''
                set -eu
                test ! -f .quality-gate-failed
                echo "SUCCESS: Python quality gates passed"
              '''
            }
          }

          stage('Build and push immutable image') {
            container('kaniko') {
              sh '''
                GIT_COMMIT="${GIT_COMMIT:-$(git rev-parse HEAD)}"
                if [ -n "${CHANGE_ID:-}" ]; then
                  IMAGE_TAG="pr-${CHANGE_ID}-${GIT_COMMIT}"
                else
                  IMAGE_TAG="${GIT_COMMIT}"
                fi
                /kaniko/executor \
                  --context "$WORKSPACE" \
                  --dockerfile "$WORKSPACE/Dockerfile" \
                  --destination "$REGISTRY/$IMAGE_NAME:$IMAGE_TAG" \
                  --registry-certificate "$REGISTRY=/kaniko/ssl/certs/additional-ca-cert-bundle.crt" \
                  --snapshot-mode=redo \
                  --cache=true \
                  --compressed-caching=false \
                  --cache-repo "$REGISTRY/$IMAGE_NAME-cache"
              '''
            }
          }

          if (env.CHANGE_ID == null) {
            stage('Deploy development') {
              container('kubectl') {
                sh '''
                  set -eu

                  GIT_COMMIT="${GIT_COMMIT:-$(git rev-parse HEAD)}"

                  touch "$WORKSPACE/.deployment-attempted"

                  rendered_manifest="$(mktemp)"
                  sed "s|IMAGE_PLACEHOLDER|$REGISTRY/$IMAGE_NAME:$GIT_COMMIT|" kubernetes/development.yaml > "$rendered_manifest"
                  kubectl apply -f "$rendered_manifest"

                  kubectl -n "$NAMESPACE" annotate deployment/"$DEPLOYMENT" \
                    vyb.sparinfosys.com/git-commit="$GIT_COMMIT" --overwrite

                  if ! kubectl -n "$NAMESPACE" rollout status deployment/"$DEPLOYMENT" --timeout=20m; then
                    echo "ERROR: Deployment rollout did not complete within 20 minutes. Capturing diagnostics and rolling back."
                    kubectl -n "$NAMESPACE" get pods -l app.kubernetes.io/name="$DEPLOYMENT" -o wide || true
                    kubectl -n "$NAMESPACE" describe deployment "$DEPLOYMENT" || true
                    kubectl -n "$NAMESPACE" rollout undo deployment/"$DEPLOYMENT" || true
                    exit 1
                  fi

                  kubectl -n "$NAMESPACE" wait --for=condition=available deployment/"$DEPLOYMENT" --timeout=2m
                  kubectl -n "$NAMESPACE" get deployment "$DEPLOYMENT" -o wide
                  echo "SUCCESS: $DEPLOYMENT rolled out and is available in namespace $NAMESPACE at commit $GIT_COMMIT"
                '''
              }
            }
          }
        }
      }
      }
    } catch (err) {
      pipelineError = err
      currentBuild.result = 'FAILURE'
      throw err
    } finally {
      def result = currentBuild.currentResult ?: 'SUCCESS'
      try {
        emailext(
          attachLog: true,
          compressLog: true,
          to: env.JENKINS_NOTIFICATION_TO,
          subject: "[Jenkins] ${result}: ${env.JOB_NAME} #${env.BUILD_NUMBER}",
          body: """Job: ${env.JOB_NAME}
Build: #${env.BUILD_NUMBER}
Status: ${result}
Duration: ${currentBuild.durationString}
Branch: dev
Commit: ${env.GIT_COMMIT ?: 'N/A'}
Build URL: ${env.BUILD_URL}
Error: ${pipelineError?.message ?: 'None'}
"""
        )
      } catch (notificationError) {
        echo "Email notification failed: ${notificationError.message}"
      }
    }
  }
}
