const path = require('path');
const MiniCssExtractPlugin     = require('mini-css-extract-plugin');
const CopyWebpackPlugin = require('copy-webpack-plugin');
const TerserWebpackPlugin = require('terser-webpack-plugin');

module.exports = {
  mode: "production",
  entry: {
    home_script: './src/_home/script.js',

    // privacy_script: './_privacypolicy/script.js',
    // refund_script: './_refund/script.js',
    // terms_script: './_terms/script.js',

    tailwind:        './src/globals/tailwind.css',  // ← include your Tailwind source
  },
  devtool: false, // Use source maps without eval
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: '[name].bundle.js',
    devtoolModuleFilenameTemplate: info => `file:///${info.resourcePath}`,
    clean: true, // Clean output directory before each build
  },
  module: {
    rules: [
      {
        test: /\.js$/, // Target JavaScript files
        exclude: /node_modules/, // Exclude node_modules
        use: {
          loader: 'babel-loader', // Use Babel loader if you want to transpile ES6+
          options: {
            presets: ['@babel/preset-env'] // Specify presets if using Babel
          }
        }
      },
      {
        test: /\.css$/i,
        include: path.resolve(__dirname, 'src/globals'),
        use: [
          MiniCssExtractPlugin.loader,  // extract to file
          'css-loader',                 // resolves imports
          'postcss-loader'              // runs Tailwind + autoprefixer
        ]
      },
      {
        test: /\.(png|jpe?g|gif|svg|woff2?|ttf|eot)$/, // Handle images and fonts
        type: 'asset/resource', // Use the built-in asset module
        generator: {
          filename: './src/assets/[hash][ext][query]' // Specify output path for assets
        }
      }
    ]
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: 'tailwind.css'          // emits dist/tailwind.css
    }),
    new CopyWebpackPlugin({
      patterns: [
        // { from: './src/404.html', to: '404.html' },
        { from: './src/_home/index.html', to: 'index.html' },

        // { from: './_privacypolicy/index.html', to: 'privacy-policy.html' },
        // { from: './_refund/index.html', to: 'refund-policy.html' },
        // { from: './_terms/index.html', to: 'terms.html' },

        // { from: './src/robots.txt',       to: 'robots.txt' },
        // { from: './src/sitemap.xml',       to: 'sitemap.xml' },
        // { from: './src/locales', to: 'locales' },
        // { from: './src/assets', to: 'assets' }
      ]
    })
  ],
  optimization: {
    minimize: true, // Enable minification
    minimizer: [
      new TerserWebpackPlugin({
        extractComments: false,
        terserOptions: {
          compress: {
            drop_console: true, // Remove console logs
          },
          output: {
            comments: false, // Removes comments
          },
        },
      }),
    ],
  }
};
