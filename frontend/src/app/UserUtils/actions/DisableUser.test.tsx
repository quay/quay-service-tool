import { mount, shallow } from 'enzyme';
import React from 'react';
import axios from "axios";
import { DisableUser } from './DisableUser';
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

async function typeUsername(view, username){
    let input = view.find("input#disable-username").at(0);
    await act(async () => {
        input.getDOMNode().setAttribute('value', username);
        input.simulate('change', {currentTarget: input});
    });
}

async function typeQueue(view, queue){
    let queueInput = view.find("input#queue").at(0);
    await act(async () => {
        queueInput.getDOMNode().setAttribute('value', queue);
        queueInput.simulate('change', {currentTarget: queueInput});
    });
}

// Clicking button triggers other async requests and updates state
async function asyncClickButton(view, button){
    await act(async () => {
        button.simulate('click');
        await flushPromises(); // Pauses execution of tests until promises in the component have been resolved
        view.update(); // Sync enzyme component tree with the react component tree
    });
}

describe('Disable users tests', ()=>{
    it('should render', () => {
        const view = mount(<DisableUser />);
        expect(view).toMatchSnapshot();
    });

    it('Should alert error if username is not provided', () => {
        const view = mount(<DisableUser />);
        view.find('button#disable-user-submit').simulate('click');
        expect(view.find('Alert#disable-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#disable-user-alert').text().includes('Please enter a username')).toBe(true);
    })

    it('Should alert error if queue is not provided', async () => {
        const view = mount(<DisableUser />);
        await typeUsername(view, 'test');
        view.find('button#disable-user-submit').simulate('click');
        expect(view.find('Alert#disable-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#disable-user-alert').text().includes('Please enter a queue name')).toBe(true);
    })

    it('Should alert if given username isn\'t found in backend', async () => {
        let username = 'nonexistentusername';
        mocked(HttpService, true).axiosClient.get.mockRejectedValue({response: {status: 404, data:{message: `Could not find user ${username}`}}});
        const view = mount(<DisableUser />);
        await typeUsername(view, username);
        await typeQueue(view, 'testqueue');
        await asyncClickButton(view, view.find('button#disable-user-submit'));
        expect(view.find('Alert#disable-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#disable-user-alert').text().includes(`User ${username} does not exist`)).toBe(true);
    })

    it('Should alert if user is already disabled', async ()=>{
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {enabled: false}});
        let username = "existingusername";
        const view = mount(<DisableUser />);
        await typeUsername(view, username);
        await typeQueue(view, 'testqueue');
        await asyncClickButton(view, view.find('button#disable-user-submit'));
        expect(view.find('Alert#disable-user-alert').props()).toHaveProperty('variant', 'danger');
        expect(view.find('Alert#disable-user-alert').text().includes(`User ${username} is already disabled`)).toBe(true);
    })

    it('Should disable user', async()=>{
        let username = "existinguser";
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {user: username, enabled: true}});
        mocked(HttpService, true).axiosClient.put.mockResolvedValue({data: {message: "User updated successfully", user: "existinguser",enabled: false}});
        const view = mount(<DisableUser />);
        await typeUsername(view, username);
        await typeQueue(view, 'testqueue');
        await asyncClickButton(view, view.find('button#disable-user-submit'));
        expect(view.find('Modal').props()).toHaveProperty('isOpen', true);
        expect(view.find('Modal').props()).toHaveProperty('title', `Disable user ${username}?`);
        await asyncClickButton(view, view.find('button#disable-user-confirm'));
        expect(view.find('Alert#disable-user-alert').props()).toHaveProperty('variant', 'success');
        expect(view.find('Alert#disable-user-alert').text().includes(`User ${username} disabled`)).toBe(true);
        expect(view.find('Modal').exists()).toBe(false);
    })
});
