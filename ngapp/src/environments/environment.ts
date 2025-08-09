export const environment = {
    production: false,
    API_URL: '/api', // to avoid CORS problems, I don't use this: 'http://localhost:8000/api' but include proxy.json.conf
    WS_URL: 'ws://localhost:8000/api/ws',
    DOUBLE_CLICK_DELAY: 250,
};
