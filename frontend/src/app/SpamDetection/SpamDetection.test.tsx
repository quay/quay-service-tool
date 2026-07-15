import React from 'react';
import { mocked } from 'ts-jest/utils';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
            rescan_terminal_records: 0,
          },
        },
      })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({
        data: {
          actions: [
            {
              created_at: '2026-07-15T01:00:00',
              namespace_name: 'publicns',
              repository_name: 'spam',
              action: 'quarantine',
              from_status: 'flagged',
              to_status: 'quarantined',
              operator: 'reviewer',
            },
          ],
        },
      });

    render(<SpamDetection />);

    expect(await screen.findByText('Default classifier')).toBeTruthy();
    expect(await screen.findByText('20260620.1')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Policy' }));
    expect(await screen.findByLabelText('Rescan unchanged terminal review records')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Audit' }));
    expect(await screen.findByText('flagged -> quarantined')).toBeTruthy();
  });

  it('requires confirmation and redaction text before redacting', async () => {
    mocked(HttpService, true).axiosClient.get
      .mockResolvedValueOnce({ data: { classifiers: [] } })
      .mockResolvedValueOnce({
        data: {
          policy: {
            scan_threshold: 0.9,
            ingress_threshold: 0.9,
            include_private: 0,
            scan_dry_run: 1,
            rescan_terminal_records: 0,
          },
        },
      })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({
        data: {
          records: [
            {
              uuid: 'record-1',
              namespace_name: 'publicns',
              repository_name: 'spam',
              status: 'quarantined',
              classifier_score: 0.99,
            },
          ],
        },
      })
      .mockResolvedValueOnce({ data: { actions: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { actions: [] } });
    mocked(HttpService, true).axiosClient.post.mockResolvedValue({ data: { record: { uuid: 'record-1' } } });

    render(<SpamDetection />);

    fireEvent.click(await screen.findByText('Review'));
    fireEvent.click(await screen.findByText('Redact'));

    const confirm = await screen.findByText('Confirm');
    expect(confirm.closest('button')?.hasAttribute('disabled')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('Redacted description'), {
      target: { value: '[redacted]' },
    });
    fireEvent.click(confirm);

    await waitFor(() => {
      expect(mocked(HttpService, true).axiosClient.post).toHaveBeenCalledWith(
        '/spam-detection/review/record-1/redact',
        { redacted_description: '[redacted]' },
      );
    });
  });
});
