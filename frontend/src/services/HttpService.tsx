import axios from "axios";
import UserService from "./UserService";

const HttpMethods = {
  GET: 'GET',
  POST: 'POST',
  DELETE: 'DELETE',
};

const _axios = axios.create();

const configure = () => {
  _axios.interceptors.request.use((config) => {
    if (process.env.NODE_ENV !== "production") {
      return config;
    }
    else if (UserService.isLoggedIn()) {
      const cb = () => {
        config.headers.Authorization = `Bearer ${UserService.getToken()}`;
        return Promise.resolve(config);
      };
      return UserService.updateToken(cb);
    }
  },function(error) {
    return Promise.reject(error);
  });
};

const axiosClient = _axios;

const HttpService = {
  HttpMethods,
  configure,
  axiosClient,
};

export default HttpService;
