import { mount, shallow } from 'enzyme';
import React from 'react';
import axios from "axios";
import { EnableUser } from './EnableUser';
import { List, Modal } from '@patternfly/react-core';
import HttpService from "../../../services/HttpService";
import { mocked } from 'ts-jest/utils';
import {act} from 'react-dom/test-utils';

jest.mock('../../../services/HttpService', () => ({
    axiosClient: {
        get: jest.fn(),
        put: jest.fn()
    }
}));

// Wait for all pending promises to resolve
// Adds promise to end of event loop and waits for it to resolve
function flushPromises() {
    return new Promise(resolve => setImmediate(resolve));
}

async function typeAndSubmitUsername(view, username){
    let input = view.find("input#enable-username").at(0);
    await act(async () => {
        input.getDOMNode().setAttribute('value', username);
        input.simulate('change', {currentTarget: input});
    });
    await act(async () => {
        view.find('button#enable-user-submit').simulate('click');
        await flushPromises(); // Pauses execution of tests until promises in the component have been resolved
        view.update(); // Sync enzyme component tree with the react component tree
    });
}

describe('Enable users tests', ()=>{
    it('should render', () => {
        const view = mount(<EnableUser />);
        expect(view).toMatchSnapshot();
    });

    it('Should alert error if username is not provided', () => {
        const view = mount(<EnableUser />);
        view.find('button#enable-user-submit').simulate('click');
        expect(view.find('Alert#enable-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#enable-user-alert').text().includes('Please enter a username')).toBe(true);
    })

    it('Should alert if given username isn\'t found in backend', async () => {
        let username = 'nonexistentusername';
        mocked(HttpService, true).axiosClient.get.mockRejectedValue({response: {status: 404, data:{message: `Could not find user ${username}`}}});
        const view = mount(<EnableUser />);
        await typeAndSubmitUsername(view, username);
        expect(view.find('Alert#enable-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#enable-user-alert').text().includes(`User ${username} does not exist`)).toBe(true);
    })

    it('Should alert if user is already enabled', async ()=>{
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {enabled: true}});
        let username = "nonexistentusername";
        const view = mount(<EnableUser />);
        await typeAndSubmitUsername(view, username);
        expect(view.find('Alert#enable-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#enable-user-alert').text().includes(`User ${username} is already enabled`)).toBe(true);
    })

    it('Should enable user', async()=>{
        let username = "existinguser";
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {user: username, enabled: false}});
        mocked(HttpService, true).axiosClient.put.mockResolvedValue({data: {message: "User updated successfully", user: "existinguser",enabled: true}});
        const view = mount(<EnableUser />);
        await typeAndSubmitUsername(view, username);
        expect(view.find('Modal').props()).toHaveProperty('isOpen', true);
        expect(view.find('Modal').props()).toHaveProperty('title', `Enable user ${username}?`);
        await act(async () => {
            view.find('button#enable-user-confirm').simulate('click');
            await flushPromises(); 
            view.update();
        });
        expect(view.find('Alert#enable-user-alert').props()).toHaveProperty('variant', 'success');
        expect(view.find('Alert#enable-user-alert').text().includes(`User ${username} enabled`)).toBe(true);
        expect(view.find('Modal').exists()).toBe(false);
    })
});
