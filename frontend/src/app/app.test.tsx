import * as React from 'react';
import App from '@app/index';
import { mount, shallow } from 'enzyme';
import { Button } from '@patternfly/react-core';
import HttpService from '../services/HttpService';
import { act } from 'react-dom/test-utils';

jest.mock('../services/HttpService', () => ({
  axiosClient: {
    get: jest.fn(),
    put: jest.fn(),
    post: jest.fn(),
    delete: jest.fn(),
  },
}));

describe('App tests', () => {
  beforeEach(() => {
    (HttpService.axiosClient.get as jest.Mock).mockResolvedValue({ data: { messages: [] } });
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test('should render default App component', () => {
    const view = shallow(<App />);
    expect(view).toMatchSnapshot();
  });

  it('should render a nav-toggle button', async () => {
    let wrapper;
    await act(async () => {
      wrapper = mount(<App />);
      await Promise.resolve();
    });
    wrapper.update();
    const button = wrapper.find(Button);
    expect(button.exists()).toBe(true);
    wrapper.unmount();
  });

  it('should hide the sidebar on smaller viewports', async () => {
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 600 });
    let wrapper;
    await act(async () => {
      wrapper = mount(<App />);
      await Promise.resolve();
      window.dispatchEvent(new Event('resize'));
    });
    wrapper.update();
    expect(wrapper.find('#page-sidebar').hasClass('pf-m-collapsed')).toBeTruthy();
    wrapper.unmount();
  });

  it.skip('should expand the sidebar on larger viewports', () => {
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1200 });
    const wrapper = mount(<App />);
    window.dispatchEvent(new Event('resize'));
    expect(wrapper.find('#page-sidebar').hasClass('pf-m-expanded')).toBeTruthy();
  });

  it.skip('should hide the sidebar when clicking the nav-toggle button', () => {
    Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 1200 });
    const wrapper = mount(<App />);
    window.dispatchEvent(new Event('resize'));
    const button = wrapper.find('#nav-toggle').hostNodes();
    expect(wrapper.find('#page-sidebar').hasClass('pf-m-expanded')).toBeTruthy();
    button.simulate('click');
    expect(wrapper.find('#page-sidebar').hasClass('pf-m-collapsed')).toBeTruthy();
    expect(wrapper.find('#page-sidebar').hasClass('pf-m-expanded')).toBeFalsy();
  });
});
