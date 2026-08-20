const config = require('./webpack.dev');

describe('development proxy', () => {
  it('routes auth separately and sends application requests to the backend', () => {
    const [authProxy, backendProxy] = config.devServer.proxy;

    expect(authProxy.context).toBe('/auth');
    expect(backendProxy.context('/spam-detection/health')).toBe(true);
    expect(backendProxy.context('/api/v1/user')).toBe(true);
    expect(backendProxy.context('/auth/realms/quay')).toBe(false);
  });
});
