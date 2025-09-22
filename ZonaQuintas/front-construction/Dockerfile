# Usamos nginx oficial como base
FROM nginx:alpine

# Borramos la configuración por defecto
RUN rm -rf /usr/share/nginx/html/*

# Copiamos los archivos del frontend (html + imagen) al directorio público
COPY . /usr/share/nginx/html

# Exponemos el puerto 80
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]