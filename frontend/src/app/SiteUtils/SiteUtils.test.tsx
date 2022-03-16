import React from 'react';
import { mocked } from 'ts-jest/utils';
import HttpService from "../../services/HttpService";
import {
    fireEvent,
    render,
    screen,
    waitForElementToBeRemoved,
  } from '@testing-library/react'
import { SiteUtils } from './SiteUtils';

jest.mock('../../services/HttpService', () => ({
    axiosClient: {
        get: jest.fn(),
        put: jest.fn(),
        post: jest.fn(),
        delete: jest.fn(),
    }
}));

describe('Site Utils Tests',()=>{
    var testBanners = [
        {
            id: 1,
            content: "Test Banner 1",
            uuid: "abcdefg",
            severity: "info",
            mediatype: {
                id: 1,
                name: "text/plan"
            }
        },
        {
            id: 2,
            content: "Test Banner 2",
            uuid: "1234567",
            severity: "danger",
            mediatype: {
                id: 1,
                name: "text/plan"
            }
        },
        {
            id: 2,
            content: "Updating banner message",
            uuid: "123467",
            severity: "danger",
            mediatype: {
                id: 1,
                name: "text/plan"
            }
        },
    ]
    it('should render with no banners if none are returned', async () => {
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {messages: []}});
        render(<SiteUtils />);
        const message = await screen.findByText('No existing banners');
        expect(message).toBeTruthy()
    });

    it('should render banners if they are returned', async () => {

        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {messages: testBanners}});
        render(<SiteUtils />);
        const banner1 = await screen.findByText('Test Banner 1');
        const banner2 = await screen.findByText('Test Banner 2');
        expect(banner1).toBeTruthy()
        expect(banner2).toBeTruthy()
    });

    it('should be able to add banner and view update', async () => {
        mocked(HttpService, true).axiosClient.get.mockImplementationOnce(() => Promise.resolve({data: {messages: []}}))
            .mockImplementationOnce(() => Promise.resolve({data: {messages: [{
                id: 1,
                content: "This is a new banner",
                uuid: "abcdefg",
                severity: "info",
                mediatype: {
                    id: 1,
                    name: "text/plan"
                }
            }]}}))
        mocked(HttpService, true).axiosClient.post.mockResolvedValue({});
        render(<SiteUtils />);
        const textArea = screen.getByPlaceholderText('Enter new message');
        fireEvent.change(textArea, {target: {value: 'This is a new banner'}})
        fireEvent( screen.getByText('Save'), new MouseEvent('click', { bubbles: true, cancelable: true, }), );
        const response = await screen.findByText('Succeeded');
        expect(response).toBeTruthy()
        expect((textArea as HTMLInputElement).value).toBe('');
        const banner = await screen.findByText('This is a new banner');
        expect(banner).toBeTruthy()
    });

    it('should be able to edit banner and view update', async () => {
        mocked(HttpService, true).axiosClient.get.mockImplementationOnce(() => Promise.resolve({data: {messages: [testBanners[0]]}}))
            .mockImplementationOnce(() => Promise.resolve({data: {messages: [testBanners[2]]}}))
        mocked(HttpService, true).axiosClient.put.mockResolvedValue({});
        render(<SiteUtils />);
        const editButton = await screen.findByText('edit');
        fireEvent( editButton, new MouseEvent('click', { bubbles: true, cancelable: true, }), );
        const textArea = document.getElementById('message-form') as HTMLInputElement;
        expect(textArea.value).toBe('Test Banner 1'); 
        fireEvent.change(textArea, {target: {value: 'Updating banner message'}});
        fireEvent( screen.getByText('Save'), new MouseEvent('click', { bubbles: true, cancelable: true, }), );
        const response = await screen.findByText('Succeeded');
        expect(response).toBeTruthy()
        expect(textArea.value).toBe('');
        const banner = await screen.findByText('Updating banner message');
        expect(banner).toBeTruthy()
    });

    it('should be able to delete banner and view update', async () => {
        mocked(HttpService, true).axiosClient.get.mockImplementationOnce(() => Promise.resolve({data: {messages: [testBanners[0]]}}))
            .mockImplementationOnce(() => Promise.resolve({data: {messages: []}}));
        mocked(HttpService, true).axiosClient.delete.mockResolvedValue({});
        render(<SiteUtils />);
        const deleteButton = await screen.findByText('delete');
        fireEvent( deleteButton, new MouseEvent('click', { bubbles: true, cancelable: true, }), );
        const confirmButton = await screen.findByText('Confirm');
        fireEvent( confirmButton, new MouseEvent('click', { bubbles: true, cancelable: true, }), );
        await waitForElementToBeRemoved(() => screen.getByText('Test Banner 1'));
        const banner = screen.queryByText('Test Banner 1')
        expect(banner).toBeNull();
    });

    it('should provide error if banners are unable to be retrieved', async () => {
        mocked(HttpService, true).axiosClient.get.mockRejectedValue({response: {status: 500, data:{message: `Unable to fetch banners`}}});
        render(<SiteUtils />);
        const errorMessage = await screen.findByText('Failed to load banners');
        expect(errorMessage).toBeTruthy()
    });

    it('should provide error if banner update fails', async () => {
        mocked(HttpService, true).axiosClient.get.mockResolvedValue({data: {messages: []}});
        mocked(HttpService, true).axiosClient.post.mockRejectedValue({response: {status: 500, data:{message: `Unable to create a new banner`}}});
        render(<SiteUtils />);
        const textArea = screen.getByPlaceholderText('Enter new message');
        fireEvent.change(textArea, {target: {value: 'This is a new banner'}})
        fireEvent( screen.getByText('Save'), new MouseEvent('click', { bubbles: true, cancelable: true, }), );
        const errorMessage = await screen.findByText('Unable to create a new banner');
        expect(errorMessage).toBeTruthy()
    });
})
