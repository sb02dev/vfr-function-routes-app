docker build --build-arg APP_ENV=docker -t vfr-function-routes-app:v0.1 .
docker run -p 8080:8080 vfr-function-routes-app:v0.1
