FROM nginx:alpine
COPY . /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN echo 'window.TASKFLOW_API = "/api";' > /usr/share/nginx/html/config.js
