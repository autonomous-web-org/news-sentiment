// postcss.config.js
module.exports = {
  plugins: [
    require('@tailwindcss/postcss'),  // Tailwind v4 PostCSS plugin :contentReference[oaicite:1]{index=1}
    require('autoprefixer')           // autoprefixer for vendor prefixes :contentReference[oaicite:2]{index=2}
  ]
}
