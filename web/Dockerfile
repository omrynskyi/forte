# Forte web image (used by `docker compose --profile app up` and container-based production).
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG FORTE_API_URL=http://api:8000
ENV FORTE_API_URL=$FORTE_API_URL
RUN npm run build

FROM node:24-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "start"]
