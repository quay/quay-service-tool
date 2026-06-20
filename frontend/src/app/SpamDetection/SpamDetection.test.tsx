import React from 'react';
import { mocked } from 'ts-jest/utils';
import { render, screen } from '@testing-library/react';
import HttpService from 'src/services/HttpService';
import { SpamDetection } from './SpamDetection';

jest.mock('src/services/HttpService', () => ({
  axiosClient: {
    get: jest.fn(),
    put: jest.fn(),
    post: jest.fn(),
  },
}));

describe('Spam Detection', () => {
  it('renders classifier data from the API', async () => {
    mocked(HttpService, true).axiosClient.get
      .mockResolvedValueOnce({
        data: {
          classifiers: [
            {
              uuid: 'classifier-1',
              name: 'Default classifier',
              enabled: 1,
              artifact_version: '20260620.1',
              artifact_sha256: 'abc123',
            },
          ],
        },
      })
      .mockResolvedValueOnce({
        data: {
          policy: {
            scan_threshold: 0.9,
            ingress_threshold: 0.9,
            include_private: 0,
            scan_dry_run: 1,
          },
        },
      })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({ data: { records: [] } });

    render(<SpamDetection />);

    expect(await screen.findByText('Default classifier')).toBeTruthy();
    expect(await screen.findByText('20260620.1')).toBeTruthy();
  });
});
