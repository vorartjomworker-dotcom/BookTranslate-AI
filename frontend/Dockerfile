FROM node:22-alpine AS build

WORKDIR /app
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
ENV NODE_ENV=production
WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev && npm cache clean --force
COPY --from=build /app/.next ./.next

USER node
EXPOSE 3000
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]
