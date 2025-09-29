const path = require('path');
const CopyWebpackPlugin = require('copy-webpack-plugin');
const TerserWebpackPlugin = require('terser-webpack-plugin');

module.exports = {
  mode: "production",
  entry: {
    popup: './src/home/script.js',       // Entry point for script.js
    global: './src/global.js',
    // ads: './src/ads.js', // Entry point for components.js
    // license: './src/license.js', // Entry point for components.js
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
        test: /\.css$/,
        use: ['style-loader', 'css-loader']
      },
      {
        test: /\.(png|jpe?g|gif|svg|woff2?|ttf|eot)$/, // Handle images and fonts
        type: 'asset/resource', // Use the built-in asset module
        generator: {
          filename: './assets/[hash][ext][query]' // Specify output path for assets
        }
      }
    ]
  },
  plugins: [
    new CopyWebpackPlugin({
      patterns: [
        { from: './src/home/index.html', to: 'index.html' },
        { from: './src/home/style.css', to: 'index.css' },
        // { from: './src/assets', to: 'assets' },
        { from: './src/locales', to: '_locales' },
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
            drop_console: false, // Remove console logs
          },
          output: {
            comments: false, // Removes comments
          },
        },
      }),
    ],
  }
};
