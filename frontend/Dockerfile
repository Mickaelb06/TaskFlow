FROM nginx:alpine
COPY . /usr/share/nginx/html
# modèle rendu au démarrage par l'image nginx (envsubst) ; NGINX_LOCAL_RESOLVERS est fourni par l'image
COPY nginx.conf /etc/nginx/templates/default.conf.template
ENV PORT=80 API_UPSTREAM=api:8000 NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
RUN echo 'window.TASKFLOW_API = "/api";' > /usr/share/nginx/html/config.js
