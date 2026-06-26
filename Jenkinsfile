pipeline {
    agent any

    environment {
        SERVER_HOST = '217.216.72.181'
        SERVER_USER = 'root'
        DEPLOY_PATH  = '/opt/viewer'
    }

    stages {
        stage('Deploy to Server') {
            steps {
                sshagent(credentials: ['creatio-server']) {
                    sh """
                        ssh -o StrictHostKeyChecking=no ${SERVER_USER}@${SERVER_HOST} '
                            cd ${DEPLOY_PATH} &&
                            git pull &&
                            docker compose up -d --build viewer
                        '
                    """
                }
            }
        }
    }

    post {
        success {
            echo 'Deploy berhasil. Viewer sudah running dengan kode terbaru.'
        }
        failure {
            echo 'Deploy gagal. Cek log di atas.'
        }
    }
}
