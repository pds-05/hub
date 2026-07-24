pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }

    parameters {
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: '要构建的 GitLab 分支')
        booleanParam(name: 'RUN_SONAR', defaultValue: true, description: '是否执行 SonarQube 代码审查')
        booleanParam(name: 'BUILD_AGENT', defaultValue: true, description: '是否构建并推送 monitor-agent 镜像')
        booleanParam(name: 'DEPLOY_TO_K8S', defaultValue: true, description: '是否发布到 Kubernetes')
    }

    environment {
        HARBOR_REGISTRY = '114.55.117.211:18080'
        HARBOR_PROJECT = 'monitor-platform'
        BACKEND_IMAGE = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/monitor-backend"
        FRONTEND_IMAGE = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/monitor-frontend"
        AGENT_IMAGE = "${HARBOR_REGISTRY}/${HARBOR_PROJECT}/monitor-agent"
        K8S_NAMESPACE = 'platform'
        IMAGE_TAG = "${env.BUILD_NUMBER}-${env.GIT_COMMIT ? env.GIT_COMMIT.take(8) : 'manual'}"
    }

    stages {
        stage('拉取源码') {
            steps {
                checkout scm
                script {
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${sh(script: 'git rev-parse --short=8 HEAD', returnStdout: true).trim()}"
                }
                sh 'git log -1 --oneline'
            }
        }

        stage('后端语法检查') {
            steps {
                sh '''
                    cd backend
                    python3 -m compileall app
                '''
            }
        }

        stage('前端构建检查') {
            steps {
                sh '''
                    cd frontend
                    npm ci
                    npm run build
                '''
            }
        }

        stage('Agent 语法检查') {
            when { expression { return params.BUILD_AGENT } }
            steps {
                sh '''
                    cd agent
                    python3 -m compileall agent.py
                '''
            }
        }

        stage('SonarQube 代码审查') {
            when { expression { return params.RUN_SONAR } }
            steps {
                withSonarQubeEnv('sonarqube') {
                    sh 'sonar-scanner -Dsonar.projectVersion=${IMAGE_TAG}'
                }
            }
        }

        stage('SonarQube 质量门禁') {
            when { expression { return params.RUN_SONAR } }
            steps {
                timeout(time: 5, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('登录 Harbor') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'harbor-admin', usernameVariable: 'HARBOR_USERNAME', passwordVariable: 'HARBOR_PASSWORD')]) {
                    sh '''
                        echo "$HARBOR_PASSWORD" | docker login "$HARBOR_REGISTRY" -u "$HARBOR_USERNAME" --password-stdin
                    '''
                }
            }
        }

        stage('构建镜像') {
            parallel {
                stage('构建后端镜像') {
                    steps {
                        sh '''
                            docker build -t "$BACKEND_IMAGE:$IMAGE_TAG" -t "$BACKEND_IMAGE:latest" backend
                        '''
                    }
                }
                stage('构建前端镜像') {
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
                stage('构建 Agent 镜像') {
                    when { expression { return params.BUILD_AGENT } }
                    steps {
                        sh '''
                            docker build -t "$AGENT_IMAGE:$IMAGE_TAG" -t "$AGENT_IMAGE:v1" agent
                        '''
                    }
                }
            }
        }

        stage('推送镜像到 Harbor') {
            steps {
                sh '''
                    docker push "$BACKEND_IMAGE:$IMAGE_TAG"
                    docker push "$BACKEND_IMAGE:latest"
                    docker push "$FRONTEND_IMAGE:$IMAGE_TAG"
                    docker push "$FRONTEND_IMAGE:latest"
                '''
                script {
                    if (params.BUILD_AGENT) {
                        sh '''
                            docker push "$AGENT_IMAGE:$IMAGE_TAG"
                            docker push "$AGENT_IMAGE:v1"
                        '''
                    }
                }
            }
        }

        stage('发布到 Kubernetes') {
            when { expression { return params.DEPLOY_TO_K8S } }
            steps {
                withCredentials([file(credentialsId: 'kubeconfig-platform', variable: 'KUBECONFIG_FILE')]) {
                    sh '''
                        export KUBECONFIG="$KUBECONFIG_FILE"
                        kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-backend monitor-backend="$BACKEND_IMAGE:$IMAGE_TAG"
                        kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-backend --timeout=180s
                        kubectl -n "$K8S_NAMESPACE" set image deployment/monitor-frontend monitor-frontend="$FRONTEND_IMAGE:$IMAGE_TAG"
                        kubectl -n "$K8S_NAMESPACE" rollout status deployment/monitor-frontend --timeout=180s
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker logout "$HARBOR_REGISTRY" || true'
        }
        success {
            echo "CI/CD 完成，镜像版本：${IMAGE_TAG}"
        }
        failure {
            echo 'CI/CD 失败，请查看失败阶段日志。'
        }
    }
}

