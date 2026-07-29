pipeline {
    agent any

    options {
        timestamps()
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    parameters {
        booleanParam(name: 'RUN_SONAR', defaultValue: true, description: 'Run SonarQube analysis and quality gate')
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
                        test "$(kubectl auth can-i get scrapeconfigs.monitoring.coreos.com -n monitoring)" = "yes"
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
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
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
                              --build-arg VITE_GRAFANA_URL=http://114.55.117.211:31000 \
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

                                kubectl -n "$K8S_NAMESPACE" patch deployment monitor-backend \
                                  --type merge \
                                  -p '{"spec":{"template":{"spec":{"serviceAccountName":"monitor-backend"}}}}'

                                kubectl -n "$K8S_NAMESPACE" set env deployment/monitor-backend \
                                  PROMETHEUS_SCRAPE_CONFIG_ENABLED=true \
                                  PROMETHEUS_SCRAPE_CONFIG_NAMESPACE=monitoring \
                                  PROMETHEUS_SCRAPE_CONFIG_API_VERSION=monitoring.coreos.com/v1alpha1 \
                                  PROMETHEUS_SCRAPE_CONFIG_LABELS_JSON='{"release":"monitoring"}' \
                                  PROMETHEUS_TARGET_SCRAPE_INTERVAL=30s \
                                  PROMETHEUS_TARGET_SCRAPE_TIMEOUT=10s \
                                  PROMETHEUS_ALLOW_PRIVATE_TARGETS=false \
                                  TARGET_ALERT_EVALUATION_ENABLED=true \
                                  TARGET_ALERT_EVALUATION_INTERVAL_SECONDS=60

                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-backend \
                                  monitor-backend="$BACKEND_IMAGE:$IMAGE_TAG"
                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-frontend \
                                  monitor-frontend="$FRONTEND_IMAGE:$IMAGE_TAG"

                                kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-backend --timeout=180s
                                kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-frontend --timeout=180s

                                test "$(kubectl -n "$K8S_NAMESPACE" get deployment monitor-backend -o jsonpath='{.spec.template.spec.serviceAccountName}')" = "monitor-backend"
                                kubectl -n "$K8S_NAMESPACE" exec deployment/monitor-backend -- \
                                  sh -c 'test "$PROMETHEUS_SCRAPE_CONFIG_ENABLED" = "true" && test "$TARGET_ALERT_EVALUATION_ENABLED" = "true"'
                                kubectl -n "$K8S_NAMESPACE" exec deployment/monitor-backend -- python -c \
                                  'import ssl, urllib.request; token=open("/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8").read().strip(); context=ssl.create_default_context(cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"); request=urllib.request.Request("https://kubernetes.default.svc/apis/monitoring.coreos.com/v1alpha1/namespaces/monitoring/scrapeconfigs", headers={"Authorization": "Bearer " + token}); response=urllib.request.urlopen(request, context=context, timeout=10); assert response.status == 200'

                                kubectl get scrapeconfig -n monitoring -l monitor-platform-managed=true || true
                            '''
                        } catch (error) {
                            echo 'Kubernetes deployment failed. Restoring the previous application images.'
                            sh '''
                                export KUBECONFIG="$KUBECONFIG_FILE"
                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-backend \
                                  monitor-backend="$PREVIOUS_BACKEND_IMAGE" || true
                                kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-frontend \
                                  monitor-frontend="$PREVIOUS_FRONTEND_IMAGE" || true
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
