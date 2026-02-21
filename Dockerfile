FROM atendare/evolution-api:v2.1.1
EXPOSE 8080
CMD ["node", "dist/src/main.js"]
