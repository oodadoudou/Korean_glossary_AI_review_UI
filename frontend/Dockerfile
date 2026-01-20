# Build stage
FROM node:20-alpine as build

WORKDIR /app

# Copy package files from frontend directory
# Context is assumed to be project root
COPY frontend/package*.json ./

RUN npm install

# Copy frontend source code
COPY frontend/ .

RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
