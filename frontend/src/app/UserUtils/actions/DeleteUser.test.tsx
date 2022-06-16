import { mount, shallow } from 'enzyme';
import React from 'react';
import { DeleteUser } from './DeleteUser';
import HttpService from "../../../services/HttpService";
import { mocked } from 'ts-jest/utils';
import {act} from 'react-dom/test-utils';

jest.mock('../../../services/HttpService', () => ({
    axiosClient: {
        get: jest.fn(),
        put: jest.fn(),
        delete: jest.fn()
    }
}));

// Wait for all pending promises to resolve
// Adds promise to end of event loop and waits for it to resolve
function flushPromises() {
    return new Promise(resolve => setImmediate(resolve));
}

async function typeAndSubmitUsername(view, username){
    const input = view.find("input#delete-username").at(0);
    await act(async () => {
        input.getDOMNode().setAttribute('value', username);
        input.simulate('change', {currentTarget: input});
    });
    await act(async () => {
        view.find('button#delete-user-submit').simulate('click');
        await flushPromises(); // Pauses execution of tests until promises in the component have been resolved
        view.update(); // Sync enzyme component tree with the react component tree
    });
}

describe('Delete users tests', ()=>{
    it('should render', () => {
        const view = mount(<DeleteUser />);
        expect(view).toMatchSnapshot();
    });

    it('Should alert error if username is not provided', () => {
        const view = mount(<DeleteUser />);
        view.find('button#delete-user-submit').simulate('click');
        expect(view.find('Alert#delete-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#delete-user-alert').text().includes('Please enter a username')).toBe(true);
    })

    it('Should alert if given username isn\'t found in backend', async () => {
        const username = 'nonexistentusername';
        mocked(HttpService, true).axiosClient.get.mockRejectedValue({response: {status: 404, data:{message: `Could not find user ${username}`}}});
        const view = mount(<DeleteUser />);
        await typeAndSubmitUsername(view, username);
        expect(view.find('Alert#delete-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#delete-user-alert').text().includes(`User ${username} does not exist`)).toBe(true);
    })

    it('Should alert if user is already deleted', async ()=> {
        const username = "nonexistentusername";
        mocked(HttpService, true).axiosClient.delete.mockResolvedValue({data: {user: username}});
        const view = mount(<DeleteUser />);
        await typeAndSubmitUsername(view, username);
        expect(view.find('Alert#delete-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#delete-user-alert').text().includes(`User ${username} does not exist`)).toBe(true);
    })

    it('Should delete user', async()=>{
        const username = "existinguser";
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {user: username, "enabled": true}});
        mocked(HttpService, true).axiosClient.delete.mockResolvedValue({data: {message: "User deleted successfully", user: "existinguser"}});
        const view = mount(<DeleteUser />);
        await typeAndSubmitUsername(view, username);
        expect(view.find('Modal').props()).toHaveProperty('isOpen', true);
        expect(view.find('Modal').props()).toHaveProperty('title', `Delete user ${username}?`);
        await act(async () => {
            view.find('button#delete-user-confirm').simulate('click');
            await flushPromises();
            view.update();
        });
        expect(view.find('Alert#delete-user-alert').props()).toHaveProperty('variant', 'success');
        expect(view.find('Alert#delete-user-alert').text().includes(`User ${username} deleted`)).toBe(true);
        expect(view.find('Modal').exists()).toBe(false);
    })

    it('Should enable then delete diabled user', async()=>{
        const username = "existinguser";
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {user: username, "enabled": false}});
        mocked(HttpService, true).axiosClient.put.mockResolvedValue({data: {message: "User updated successfully", user: "existinguser",enabled: true}});
        mocked(HttpService, true).axiosClient.delete.mockResolvedValue({data: {message: "User deleted successfully", user: "existinguser"}});
        const view = mount(<DeleteUser />);
        await typeAndSubmitUsername(view, username);
        expect(view.find('Modal').props()).toHaveProperty('isOpen', true);
        expect(view.find('Modal').props()).toHaveProperty('title', `Delete user ${username}?`);
        await act(async () => {
            view.find('button#delete-user-confirm').simulate('click');
            await flushPromises();
            view.update();
        });
        expect(view.find('Alert#delete-user-alert').props()).toHaveProperty('variant', 'success');
        expect(view.find('Alert#delete-user-alert').text().includes(`User ${username} deleted`)).toBe(true);
        expect(view.find('Modal').exists()).toBe(false);
    })
});
