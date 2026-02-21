FROM atendare/evolution-api:v2.1.1
ENV PORT=8080
EXPOSE 8080
CMD ["node", "dist/main.js"]
