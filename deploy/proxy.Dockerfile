FROM nginx:1.27-alpine
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/nginx-routes.conf /etc/nginx/templates/snippets/simple-word-routes.conf.template
