const path = require('path');
const { merge } = require("webpack-merge");
const common = require("./webpack.common.js");
const { stylePaths } = require("./stylePaths");
const HOST = process.env.HOST || "0.0.0.0";
const PORT = process.env.PORT || "9000";

module.exports = merge(common('development'), {
  mode: "development",
  devtool: "eval-source-map",
  devServer: {
    contentBase: "./dist",
    host: HOST,
    port: PORT,
    compress: true,
    inline: true,
    historyApiFallback: true,
    hot: true,
    overlay: true,
    open: true,
    proxy: [
      {
        context: ["/auth**"],
        target: process.env.AUTH_URL || "http://0.0.0.0:8081",
        secure: false,
        changeOrigin: false
      },
      {
        context: ["!/auth**"],
        target: process.env.TARGET_URL || "http://0.0.0.0:5000",
        secure: false,
        changeOrigin: false
      }
    ],
  },
  module: {
    rules: [
      {
        test: /\.css$/,
        include: [
          ...stylePaths
        ],
        use: ["style-loader", "css-loader"]
      }
    ]
  }
});
