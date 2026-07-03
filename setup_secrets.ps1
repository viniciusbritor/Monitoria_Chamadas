# Preencha as variaveis abaixo com os dados reais do seu Firebase/Projeto
$VITE_API_URL_PROD = "https://monitoria-cx-4105010761.us-central1.run.app"
$VITE_API_URL_TEST = "https://monitoria-test-env.coherenceai.com.br"
$FIREBASE_API_KEY = "SUA_API_KEY_AQUI"
$FIREBASE_AUTH_DOMAIN = "SEU_AUTH_DOMAIN_AQUI"
$FIREBASE_PROJECT_ID = "SEU_PROJECT_ID_AQUI"
$FIREBASE_STORAGE_BUCKET = "SEU_STORAGE_BUCKET_AQUI"
$FIREBASE_MESSAGING_SENDER_ID = "SEU_MESSAGING_SENDER_ID_AQUI"
$FIREBASE_APP_ID = "SEU_APP_ID_AQUI"

# Comandos para atualizar o Secret Manager com os valores reais
echo $VITE_API_URL_PROD | gcloud secrets versions add VITE_API_URL_PROD --data-file=-
echo $VITE_API_URL_TEST | gcloud secrets versions add VITE_API_URL_TEST --data-file=-
echo $FIREBASE_API_KEY | gcloud secrets versions add FIREBASE_API_KEY --data-file=-
echo $FIREBASE_AUTH_DOMAIN | gcloud secrets versions add FIREBASE_AUTH_DOMAIN --data-file=-
echo $FIREBASE_PROJECT_ID | gcloud secrets versions add FIREBASE_PROJECT_ID --data-file=-
echo $FIREBASE_STORAGE_BUCKET | gcloud secrets versions add FIREBASE_STORAGE_BUCKET --data-file=-
echo $FIREBASE_MESSAGING_SENDER_ID | gcloud secrets versions add FIREBASE_MESSAGING_SENDER_ID --data-file=-
echo $FIREBASE_APP_ID | gcloud secrets versions add FIREBASE_APP_ID --data-file=-

Write-Host "✅ Segredos atualizados com sucesso no GCP Secret Manager!"
