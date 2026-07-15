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
    mocked(HttpService, true)
      .axiosClient.get.mockResolvedValueOnce({
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
            max_repos: 0,
          },
        },
      })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
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

    expect(await screen.findByRole('heading', { name: 'Spam detection' })).toBeTruthy();
    expect(await screen.findByText('Default classifier')).toBeTruthy();
    expect(await screen.findByText('20260620.1')).toBeTruthy();
    expect(await screen.findByRole('table', { name: 'Classifiers' })).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Policy' }));
    expect(await screen.findByLabelText('Rescan unchanged terminal review records')).toBeTruthy();
    expect(((await screen.findByLabelText('Scan all repositories')) as HTMLInputElement).checked).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'Audit' }));
    expect(await screen.findByText('flagged -> quarantined')).toBeTruthy();
  });

  it('requires confirmation and redaction text before redacting', async () => {
    mocked(HttpService, true)
      .axiosClient.get.mockResolvedValueOnce({ data: { classifiers: [] } })
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
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { actions: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
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
        { redacted_description: '[redacted]' }
      );
    });
  });

  it('requires a reason before reopening a restored record', async () => {
    mocked(HttpService, true)
      .axiosClient.get.mockResolvedValueOnce({ data: { classifiers: [] } })
      .mockResolvedValueOnce({ data: { policy: {} } })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({
        data: {
          records: [
            {
              uuid: 'record-restored',
              namespace_name: 'publicns',
              repository_name: 'spam',
              status: 'restored',
              classifier_score: 0.99,
            },
          ],
        },
      })
      .mockResolvedValueOnce({ data: { actions: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { actions: [] } });
    mocked(HttpService, true).axiosClient.post.mockResolvedValue({
      data: { record: { uuid: 'record-restored', status: 'flagged' } },
    });

    render(<SpamDetection />);

    fireEvent.click(await screen.findByText('Review'));
    fireEvent.click(await screen.findByRole('button', { name: 'Reopen review' }));

    const confirm = await screen.findByRole('button', { name: 'Confirm' });
    expect(confirm.hasAttribute('disabled')).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Reason'), {
      target: { value: 'Restore was approved in error' },
    });
    fireEvent.click(confirm);

    await waitFor(() => {
      expect(mocked(HttpService, true).axiosClient.post).toHaveBeenCalledWith(
        '/spam-detection/review/record-restored/reopen',
        { reason: 'Restore was approved in error' }
      );
    });
  });

  it('labels an existing review match for training', async () => {
    const description =
      'free casino bonus https://spam.example This deliberately long repository description gives reviewers enough context to decide whether the classifier result is correct without expanding every row by default.';
    mocked(HttpService, true)
      .axiosClient.get.mockResolvedValueOnce({ data: { classifiers: [] } })
      .mockResolvedValueOnce({ data: { policy: {} } })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({
        data: {
          records: [
            {
              uuid: 'record-1',
              namespace_name: 'publicns',
              repository_name: 'spam',
              status: 'flagged',
              classifier_score: 0.99,
              original_description: description,
              review_label: null,
            },
          ],
        },
      })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { actions: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { actions: [] } });
    mocked(HttpService, true).axiosClient.post.mockResolvedValue({
      data: { record: { uuid: 'record-1', status: 'flagged' } },
    });

    render(<SpamDetection />);

    fireEvent.click(await screen.findByText('Review'));
    expect((await screen.findByRole('link', { name: 'publicns/spam' })).getAttribute('href')).toBe(
      'https://quay.io/repository/publicns/spam'
    );
    expect(await screen.findByText(description)).toBeTruthy();
    const showMore = await screen.findByRole('button', { name: 'Show more' });
    expect(showMore.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(showMore);
    expect(await screen.findByRole('button', { name: 'Show less' })).toBeTruthy();
    fireEvent.click(await screen.findByRole('button', { name: 'Label spam' }));
    expect(await screen.findByText('Description to label')).toBeTruthy();
    expect(screen.getAllByText(description)).toHaveLength(2);
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    await waitFor(() => {
      expect(mocked(HttpService, true).axiosClient.post).toHaveBeenCalledWith(
        '/spam-detection/review/record-1/classify',
        { label: 'spam' }
      );
    });
  });

  it('exports and downloads the generated classifier artifact', async () => {
    const artifact = new Blob(['{}'], { type: 'application/json' });
    const originalCreateObjectURL = window.URL.createObjectURL;
    const originalRevokeObjectURL = window.URL.revokeObjectURL;
    const createObjectURL = jest.fn().mockReturnValue('blob:artifact');
    const revokeObjectURL = jest.fn();
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: revokeObjectURL });
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    mocked(HttpService, true)
      .axiosClient.get.mockResolvedValueOnce({
        data: {
          classifiers: [
            {
              uuid: 'classifier-1',
              name: 'Default classifier',
              enabled: 1,
              artifact_version: 'v1',
            },
          ],
        },
      })
      .mockResolvedValueOnce({ data: { policy: {} } })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { actions: [] } })
      .mockResolvedValueOnce({ data: artifact })
      .mockResolvedValueOnce({ data: { classifiers: [] } });
    mocked(HttpService, true).axiosClient.post.mockResolvedValue({
      data: { classifier: { artifact_version: 'v2' } },
    });

    render(<SpamDetection />);
    fireEvent.click(await screen.findByRole('button', { name: 'Export artifact' }));

    await waitFor(() => {
      expect(mocked(HttpService, true).axiosClient.get).toHaveBeenCalledWith(
        '/spam-detection/classifiers/classifier-1/artifact',
        { responseType: 'blob' }
      );
      expect(click).toHaveBeenCalled();
    });
    expect(createObjectURL).toHaveBeenCalledWith(artifact);
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:artifact');
    click.mockRestore();
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: originalCreateObjectURL });
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: originalRevokeObjectURL });
  });

  it('uploads and activates an imported classifier artifact', async () => {
    mocked(HttpService, true)
      .axiosClient.get.mockResolvedValueOnce({ data: { classifiers: [] } })
      .mockResolvedValueOnce({ data: { policy: {} } })
      .mockResolvedValueOnce({ data: { runs: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { records: [] } })
      .mockResolvedValueOnce({ data: { actions: [] } })
      .mockResolvedValueOnce({
        data: {
          classifiers: [
            {
              uuid: 'imported-1',
              name: 'Production v1',
              enabled: 1,
              artifact_version: 'production-v1',
            },
          ],
        },
      })
      .mockResolvedValueOnce({ data: { policy: { active_classifier_id: 1 } } });
    mocked(HttpService, true).axiosClient.post.mockResolvedValueOnce({
      data: {
        created: true,
        imported_artifact_version: 'production-v1',
        classifier: {
          uuid: 'imported-1',
          name: 'Production v1',
          enabled: 1,
          artifact_version: 'production-v1',
        },
      },
    });

    const { container } = render(<SpamDetection />);
    const file = new File(['{"version":"production-v1"}'], 'production-v1.json', {
      type: 'application/json',
    });
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });
    await waitFor(() => {
      expect((screen.getByRole('button', { name: 'Import' }) as HTMLButtonElement).disabled).toBeFalsy();
    });
    fireEvent.change(screen.getByLabelText('Name', { selector: '#artifact-name' }), {
      target: { value: 'Production v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Import' }));

    await waitFor(() => {
      expect(mocked(HttpService, true).axiosClient.post).toHaveBeenCalledWith(
        '/spam-detection/classifiers/import-artifact',
        expect.any(FormData)
      );
    });
    const formData = mocked(HttpService, true).axiosClient.post.mock.calls[0][1] as FormData;
    expect(formData.get('name')).toBe('Production v1');
    expect(formData.get('enabled')).toBe('true');
    expect(formData.get('artifact')).toBe(file);
    expect(await screen.findByText('Artifact production-v1 imported')).toBeTruthy();
  });
});
