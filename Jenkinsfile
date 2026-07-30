pipeline {
    agent any

    options {
        timestamps()
        skipDefaultCheckout(true)
        disableConcurrentBuilds(abortPrevious: true)
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    parameters {
        booleanParam(name: 'RUN_SONAR', defaultValue: true, description: 'Run SonarQube analysis and quality gate')
        booleanParam(name: 'ENFORCE_SONAR_GATE', defaultValue: false, description: 'Stop deployment when the SonarQube quality gate fails')
        booleanParam(name: 'BUILD_AGENT', defaultValue: false, description: 'Build and push the monitor-agent image')
        booleanParam(name: 'DEPLOY_TO_K8S', defaultValue: true, description: 'Deploy the release and required runtime configuration to Kubernetes')
    }

    environment {
        HARBOR_REGISTRY = '114.55.117.211:18080'
        HARBOR_PROJECT = 'monitor-platform'
        BACKEND_IMAGE = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/monitor-backend"
        FRONTEND_IMAGE = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/monitor-frontend"
        AGENT_IMAGE = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/monitor-agent"
        K8S_NAMESPACE = 'platform'
        GRAFANA_PUBLIC_URL = 'http://114.55.117.211:30080/grafana'
    }

    stages {
        stage('Checkout source') {
            steps {
                script {
                    def scmVars = checkout scm
                    def shortCommit = scmVars.GIT_COMMIT ? scmVars.GIT_COMMIT.take(8) : sh(script: 'git rev-parse --short=8 HEAD', returnStdout: true).trim()
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${shortCommit}"
                    echo "Release image tag: ${env.IMAGE_TAG}"
                }
                sh 'git log -1 --oneline'
            }
        }

        stage('Backend syntax check') {
            steps {
                sh '''
                    cd backend
                    python3 -m compileall app
                    if python3 -m coverage --version >/dev/null 2>&1 || \
                       timeout 120s python3 -m pip install --disable-pip-version-check --no-input \
                         --break-system-packages -r requirements-dev.txt; then
                        python3 -m coverage erase
                        python3 -m coverage run --source=app -m unittest discover -s tests -p 'test_unit_*.py'
                        python3 -m coverage xml -o coverage.xml
                        python3 -m coverage report
                        test -s coverage.xml
                    else
                        echo 'Coverage installation unavailable; running unit tests without a coverage report.'
                        python3 -m unittest discover -s tests -p 'test_unit_*.py'
                    fi
                '''
            }
        }

        stage('Frontend build check') {
            steps {
                sh '''
                    cd frontend
                    npm ci
                    npm run build
                '''
            }
        }

        stage('Agent syntax check') {
            when { expression { return params.BUILD_AGENT } }
            steps {
                sh '''
                    cd agent
                    python3 -m compileall agent.py
                '''
            }
        }

        stage('Kubernetes deployment preflight') {
            when { expression { return params.DEPLOY_TO_K8S } }
            steps {
                withCredentials([file(credentialsId: 'kubeconfig-platform', variable: 'KUBECONFIG_FILE')]) {
                    sh '''
                        set -eu
                        export KUBECONFIG="$KUBECONFIG_FILE"
                        test "$(kubectl auth can-i get deployments.apps -n "$K8S_NAMESPACE")" = "yes"
                        test "$(kubectl auth can-i patch deployments.apps -n "$K8S_NAMESPACE")" = "yes"
                        test "$(kubectl auth can-i create serviceaccounts -n "$K8S_NAMESPACE")" = "yes"
                        test "$(kubectl auth can-i create roles.rbac.authorization.k8s.io -n monitoring)" = "yes"
                        test "$(kubectl auth can-i create rolebindings.rbac.authorization.k8s.io -n monitoring)" = "yes"
                        test "$(kubectl auth can-i create deployments.apps -n monitoring)" = "yes"
                        test "$(kubectl auth can-i create configmaps -n monitoring)" = "yes"
                        test "$(kubectl auth can-i create services -n monitoring)" = "yes"
                        test "$(kubectl auth can-i delete services -n monitoring)" = "yes"
                        test "$(kubectl auth can-i get secret/monitoring-grafana -n monitoring)" = "yes"
                        test "$(kubectl auth can-i get scrapeconfigs.monitoring.coreos.com -n monitoring)" = "yes"
                        printf '%s\n' \
                          'apiVersion: monitoring.coreos.com/v1alpha1' \
                          'kind: ScrapeConfig' \
                          'metadata:' \
                          '  name: monitor-platform-ci-preflight' \
                          '  namespace: monitoring' \
                          'spec:' \
                          '  jobName: monitor-platform-ci-preflight' \
                          '  scheme: HTTP' \
                          '  metricsPath: /metrics' \
                          '  staticConfigs:' \
                          '    - targets: ["example.com:80"]' \
                          | kubectl apply --dry-run=server -f - >/dev/null
                    '''
                }
            }
        }

        stage('SonarQube analysis') {
            when { expression { return params.RUN_SONAR } }
            steps {
                withSonarQubeEnv('sonarqube') {
                    sh 'sonar-scanner -Dsonar.projectVersion=${IMAGE_TAG}'
                }
            }
        }

        stage('SonarQube quality gate') {
            when { expression { return params.RUN_SONAR } }
            steps {
                script {
                    def qualityGate
                    timeout(time: 5, unit: 'MINUTES') {
                        qualityGate = waitForQualityGate abortPipeline: false
                    }
                    echo "SonarQube quality gate: ${qualityGate.status}"
                    if (qualityGate.status != 'OK') {
                        if (params.ENFORCE_SONAR_GATE) {
                            error "Pipeline aborted due to quality gate failure: ${qualityGate.status}"
                        }
                        echo 'Quality gate did not pass. Continuing deployment because ENFORCE_SONAR_GATE is disabled.'
                    }
                }
            }
        }

        stage('Harbor login') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'harbor-admin', usernameVariable: 'HARBOR_USERNAME', passwordVariable: 'HARBOR_PASSWORD')]) {
                    sh '''
                        echo "$HARBOR_PASSWORD" | docker login "$HARBOR_REGISTRY" -u "$HARBOR_USERNAME" --password-stdin
                    '''
                }
            }
        }

        stage('Build images') {
            parallel {
                stage('Build backend image') {
                    steps {
                        sh '''
                            docker build -t "$BACKEND_IMAGE:$IMAGE_TAG" -t "$BACKEND_IMAGE:latest" backend
                        '''
                    }
                }

                stage('Build frontend image') {
                    steps {
                        sh '''
                            python3 -c "from pathlib import Path; p=Path('frontend/nginx.conf'); data=p.read_bytes(); p.write_bytes(data[3:] if data.startswith(bytes([239,187,191])) else data)"
                            docker build \
                              --build-arg VITE_API_BASE_URL=/api/v1 \
                              --build-arg VITE_GRAFANA_URL=http://114.55.117.211:30080/grafana \
                              -t "$FRONTEND_IMAGE:$IMAGE_TAG" \
                              -t "$FRONTEND_IMAGE:latest" \
                              frontend
                        '''
                    }
                }

                stage('Build agent image') {
                    when { expression { return params.BUILD_AGENT } }
                    steps {
                        sh '''
                            docker build -t "$AGENT_IMAGE:$IMAGE_TAG" -t "$AGENT_IMAGE:v1" agent
                        '''
                    }
                }
            }
        }

        stage('Push release images to Harbor') {
            steps {
                sh '''
                    docker push "$BACKEND_IMAGE:$IMAGE_TAG"
                    docker push "$FRONTEND_IMAGE:$IMAGE_TAG"
                '''
                script {
                    if (params.BUILD_AGENT) {
                        sh '''
                            docker push "$AGENT_IMAGE:$IMAGE_TAG"
                        '''
                    }
                }
            }
        }

        stage('Deploy to Kubernetes') {
            when { expression { return params.DEPLOY_TO_K8S } }
            steps {
                withCredentials([file(credentialsId: 'kubeconfig-platform', variable: 'KUBECONFIG_FILE')]) {
                    script {
                        env.PREVIOUS_BACKEND_IMAGE = sh(
                            script: '''
                                export KUBECONFIG="$KUBECONFIG_FILE"
                                kubectl -n "$K8S_NAMESPACE" get deployment monitor-backend -o jsonpath='{.spec.template.spec.containers[?(@.name=="monitor-backend")].image}'
                            ''',
                            returnStdout: true
                        ).trim()
                        env.PREVIOUS_FRONTEND_IMAGE = sh(
                            script: '''
                                export KUBECONFIG="$KUBECONFIG_FILE"
                                kubectl -n "$K8S_NAMESPACE" get deployment monitor-frontend -o jsonpath='{.spec.template.spec.containers[?(@.name=="monitor-frontend")].image}'
                            ''',
                            returnStdout: true
                        ).trim()

                        try {
                            sh '''
                                set -eu
                                export KUBECONFIG="$KUBECONFIG_FILE"

                                kubectl apply -f k8s/monitor-backend-scrapeconfig-rbac.yaml
                                kubectl apply -f k8s/blackbox-exporter.yaml

                                kubectl -n monitoring set env deployment/monitoring-grafana \
                                  GF_SERVER_ROOT_URL="$GRAFANA_PUBLIC_URL/" \
                                  GF_SERVER_SERVE_FROM_SUB_PATH=true \
                                  GF_AUTH_PROXY_ENABLED=true \
                                  GF_AUTH_PROXY_HEADER_NAME=X-WEBAUTH-USER \
                                  GF_AUTH_PROXY_HEADER_PROPERTY=username \
                                  GF_AUTH_PROXY_AUTO_SIGN_UP=false \
                                  GF_AUTH_PROXY_ENABLE_LOGIN_TOKEN=true \
                                  GF_AUTH_PROXY_HEADERS='Email:X-WEBAUTH-EMAIL' \
                                  GF_AUTH_ANONYMOUS_ENABLED=false

                                kubectl apply -f k8s/grafana-nodeport.yaml
                                kubectl -n monitoring rollout status deployment/monitoring-grafana --timeout=180s

                                kubectl -n "$K8S_NAMESPACE" patch deployment monitor-backend \
                                  --type merge \
                                  -p '{"spec":{"template":{"spec":{"serviceAccountName":"monitor-backend"}}}}'

                                kubectl -n "$K8S_NAMESPACE" set env deployment/monitor-backend \
                                  AGENT_PUBLIC_API_URL=http://114.55.117.211:30080/api/v1 \
                                  PROMETHEUS_SCRAPE_CONFIG_ENABLED=true \
                                  PROMETHEUS_SCRAPE_CONFIG_NAMESPACE=monitoring \
                                  PROMETHEUS_SCRAPE_CONFIG_API_VERSION=monitoring.coreos.com/v1alpha1 \
                                  PROMETHEUS_SCRAPE_CONFIG_LABELS_JSON='{"release":"monitoring"}' \
                                  PROMETHEUS_TARGET_SCRAPE_INTERVAL=30s \
                                  PROMETHEUS_TARGET_SCRAPE_TIMEOUT=10s \
                                  PROMETHEUS_ALLOW_PRIVATE_TARGETS=false \
                                  TARGET_ALERT_EVALUATION_ENABLED=true \
                                  TARGET_ALERT_EVALUATION_INTERVAL_SECONDS=60 \
                                  BLACKBOX_EXPORTER_URL=http://blackbox-exporter.monitoring.svc.cluster.local:9115 \
                                  GRAFANA_URL=http://monitoring-grafana.monitoring.svc.cluster.local:80/grafana \
                                  GRAFANA_PUBLIC_URL="$GRAFANA_PUBLIC_URL" \
                                  GRAFANA_PROVISIONING_ENABLED=true \
                                  GRAFANA_DATA_PROXY_URL=http://monitor-backend.platform.svc.cluster.local:8000/api/v1/grafana/proxy \
                                  GRAFANA_SSO_MODE=auth-proxy

                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-backend \
                                  monitor-backend="$BACKEND_IMAGE:$IMAGE_TAG"
                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-frontend \
                                  monitor-frontend="$FRONTEND_IMAGE:$IMAGE_TAG"

                                kubectl -n monitoring rollout status deployment/blackbox-exporter --timeout=180s
                                kubectl -n "$K8S_NAMESPACE" set env deployment/monitor-frontend GRAFANA_PROXY_CONFIG=v1
                                kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-backend --timeout=180s
                                kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-frontend --timeout=180s

                                test "$(kubectl -n "$K8S_NAMESPACE" get deployment monitor-backend -o jsonpath='{.spec.template.spec.serviceAccountName}')" = "monitor-backend"
                                kubectl -n "$K8S_NAMESPACE" exec deployment/monitor-backend -- \
                                  sh -c 'test "$PROMETHEUS_SCRAPE_CONFIG_ENABLED" = "true" && test "$TARGET_ALERT_EVALUATION_ENABLED" = "true"'
                                kubectl -n "$K8S_NAMESPACE" exec deployment/monitor-backend -- python -c \
                                  'import ssl, urllib.request; token=open("/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8").read().strip(); context=ssl.create_default_context(cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"); request=urllib.request.Request("https://kubernetes.default.svc/apis/monitoring.coreos.com/v1alpha1/namespaces/monitoring/scrapeconfigs", headers={"Authorization": "Bearer " + token}); response=urllib.request.urlopen(request, context=context, timeout=10); assert response.status == 200'

                                kubectl get scrapeconfig -n monitoring -l monitor-platform-managed=true || true
                                kubectl -n monitoring get deployment blackbox-exporter monitoring-grafana
                                test "$(kubectl -n monitoring get service monitoring-grafana-internal -o jsonpath='{.spec.type}')" = "ClusterIP"
                                kubectl -n monitoring delete service monitoring-grafana-nodeport --ignore-not-found
                                test -z "$(kubectl -n monitoring get service monitoring-grafana-nodeport --ignore-not-found -o name)"
                                kubectl -n "$K8S_NAMESPACE" exec deployment/monitor-backend -- python -c 'import os; assert os.environ.get("GRAFANA_PUBLIC_URL") == "http://114.55.117.211:30080/grafana"'
                                kubectl -n "$K8S_NAMESPACE" exec deployment/monitor-backend -- python -c 'import urllib.request; assert urllib.request.urlopen("http://monitoring-grafana.monitoring.svc.cluster.local:80/grafana/api/health", timeout=10).status == 200'
                                kubectl -n "$K8S_NAMESPACE" exec deployment/monitor-backend -- python -c 'import urllib.request; assert urllib.request.urlopen("http://blackbox-exporter.monitoring.svc.cluster.local:9115/-/healthy", timeout=10).status == 200'
                            '''
                        } catch (error) {
                            echo 'Kubernetes deployment failed. Restoring the previous application images.'
                            sh '''
                                export KUBECONFIG="$KUBECONFIG_FILE"
                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-backend \
                                  monitor-backend="$PREVIOUS_BACKEND_IMAGE" || true
                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-frontend \
                                  monitor-frontend="$PREVIOUS_FRONTEND_IMAGE" || true
                                kubectl -n monitoring rollout status deployment/blackbox-exporter --timeout=180s
                                kubectl -n "$K8S_NAMESPACE" set env deployment/monitor-frontend GRAFANA_PROXY_CONFIG=v1
                                kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-backend --timeout=180s || true
                                kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-frontend --timeout=180s || true
                            '''
                            throw error
                        }
                    }
                }
            }
        }

        stage('Promote stable image tags') {
            steps {
                sh '''
                    docker push "$BACKEND_IMAGE:latest"
                    docker push "$FRONTEND_IMAGE:latest"
                '''
                script {
                    if (params.BUILD_AGENT) {
                        sh 'docker push "$AGENT_IMAGE:v1"'
                    }
                }
            }
        }
    }

    post {
        always {
            sh 'docker logout "$HARBOR_REGISTRY" || true'
        }
        success {
            echo "CI/CD completed. Image tag: ${IMAGE_TAG}"
        }
        failure {
            echo 'CI/CD failed. Check the failed stage logs.'
        }
    }
}
