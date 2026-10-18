const base = require('./playwright.config');
module.exports = { ...base, use: { ...base.use,
  baseURL: process.env.LIVE_VOICE_BASE_URL || 'http://127.0.0.1:5001'
} };
