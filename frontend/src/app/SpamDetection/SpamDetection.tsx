import * as React from 'react';
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardTitle,
  Checkbox,
  Form,
  FormGroup,
  Grid,
  GridItem,
  Modal,
  ModalVariant,
  PageSection,
  Spinner,
  Tab,
  Tabs,
  TabTitleText,
  TextArea,
  TextInput,
} from '@patternfly/react-core';
import { useEffect, useState } from 'react';
import HttpService from 'src/services/HttpService';
import UserService from 'src/services/UserService';

const SPAM_DETECTION_ROLE = window.SPAM_DETECTION_ROLE || process.env.SPAM_DETECTION_ROLE;
const SPAM_DETECTION_REMEDIATION_ROLE =
  window.SPAM_DETECTION_REMEDIATION_ROLE || process.env.SPAM_DETECTION_REMEDIATION_ROLE;

type Classifier = {
  uuid: string;
  name: string;
  enabled: number;
  artifact_version?: string;
  artifact_sha256?: string;
  scan_threshold: number;
  ingress_threshold: number;
};

export const SpamDetection: React.FunctionComponent = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [classifiers, setClassifiers] = useState<Classifier[]>([]);
  const [policy, setPolicy] = useState<any>({});
  const [runs, setRuns] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [preview, setPreview] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [classifierName, setClassifierName] = useState('');
  const [trainingText, setTrainingText] = useState('');
  const [trainingLabel, setTrainingLabel] = useState('spam');
  const [csvPath, setCsvPath] = useState('');
  const [exportOutputPath, setExportOutputPath] = useState('');
  const [selectedClassifier, setSelectedClassifier] = useState('');
  const [pendingReviewAction, setPendingReviewAction] = useState<{ recordUuid: string; action: string } | null>(null);
  const [redactedDescription, setRedactedDescription] = useState('');

  const canRemediate = UserService.hasRealmRole(SPAM_DETECTION_REMEDIATION_ROLE);

  useEffect(() => {
    if (UserService.hasRealmRole(SPAM_DETECTION_ROLE)) {
      loadAll();
    }
  }, []);

  function showMessage(value: string) {
    setMessage(value);
  }

  async function loadAll() {
    setLoading(true);
    await Promise.all([loadClassifiers(), loadPolicy(), loadRuns(), loadReview()]);
    setLoading(false);
  }

  async function loadClassifiers() {
    return HttpService.axiosClient.get('/spam-detection/classifiers').then((response) => {
      setClassifiers(response.data.classifiers || []);
      const enabled = (response.data.classifiers || []).find((item) => item.enabled);
      if (enabled) {
        setSelectedClassifier(enabled.uuid);
      }
    });
  }

  async function loadPolicy() {
    return HttpService.axiosClient.get('/spam-detection/policy').then((response) => {
      setPolicy(response.data.policy || {});
    });
  }

  async function loadRuns() {
    return HttpService.axiosClient.get('/spam-detection/runs').then((response) => {
      setRuns(response.data.runs || []);
    });
  }

  async function loadReview() {
    return HttpService.axiosClient.get('/spam-detection/review').then((response) => {
      setRecords(response.data.records || []);
    });
  }

  async function createClassifier() {
    HttpService.axiosClient
      .post('/spam-detection/classifiers', {
        name: classifierName,
        enabled: classifiers.length === 0,
      })
      .then(() => {
        setClassifierName('');
        showMessage('Classifier created');
        loadClassifiers();
      })
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to create classifier'));
  }

  async function addTrainingExample() {
    if (!selectedClassifier) {
      showMessage('Select a classifier');
      return;
    }
    HttpService.axiosClient
      .post(`/spam-detection/classifiers/${selectedClassifier}/training-examples`, {
        text: trainingText,
        label: trainingLabel,
        source: 'manual_review',
      })
      .then(() => {
        setTrainingText('');
        showMessage('Training example added');
      })
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to add training example'));
  }

  async function trainClassifier() {
    if (!selectedClassifier) {
      showMessage('Select a classifier');
      return;
    }
    HttpService.axiosClient
      .post(`/spam-detection/classifiers/${selectedClassifier}/train`, {})
      .then((response) => {
        showMessage(`Artifact ${response.data.classifier.artifact_version} generated`);
        loadClassifiers();
      })
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to train classifier'));
  }

  async function exportArtifact() {
    if (!selectedClassifier) {
      showMessage('Select a classifier');
      return;
    }
    HttpService.axiosClient
      .post(`/spam-detection/classifiers/${selectedClassifier}/export-artifact`, {
        output_path: exportOutputPath || undefined,
      })
      .then((response) => {
        const exportPath = response.data.classifier.export_path;
        showMessage(
          exportPath
            ? `Artifact ${response.data.classifier.artifact_version} exported to ${exportPath}`
            : `Artifact ${response.data.classifier.artifact_version} exported`
        );
        loadClassifiers();
      })
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to export artifact'));
  }

  async function importCsv() {
    if (!selectedClassifier || !csvPath) {
      showMessage('Select a classifier and CSV path');
      return;
    }
    HttpService.axiosClient
      .post(`/spam-detection/classifiers/${selectedClassifier}/import-csv`, {
        path: csvPath,
        source: 'seed_import',
      })
      .then((response) => {
        showMessage(`${response.data.imported} examples imported`);
        setCsvPath('');
      })
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to import CSV'));
  }

  async function savePolicy() {
    HttpService.axiosClient
      .put('/spam-detection/policy', policy)
      .then(() => {
        showMessage('Policy saved');
        loadPolicy();
      })
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to save policy'));
  }

  async function runPreview() {
    setPreview(null);
    HttpService.axiosClient
      .post('/spam-detection/preview', { limit: 50 })
      .then((response) => setPreview(response.data))
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to preview scan'));
  }

  function formatHardFilters(filters: any) {
    const repositoryEmpty = filters?.repository_empty;
    const visibility = filters?.visibility;
    return [
      repositoryEmpty ? `empty:${repositoryEmpty.matched ? 'yes' : 'no'}` : null,
      visibility ? `visibility:${visibility.value || 'unknown'}` : null,
    ]
      .filter(Boolean)
      .join(', ');
  }

  async function runScan(dryRun: boolean) {
    const maxRepos = Number(policy.max_repos) > 0 ? Number(policy.max_repos) : undefined;
    HttpService.axiosClient
      .post('/spam-detection/runs', { source: 'manual', dry_run: dryRun, max_repos: maxRepos })
      .then(() => {
        showMessage('Scan completed');
        loadRuns();
        loadReview();
      })
      .catch((error) => showMessage(error.response?.data?.message || 'Unable to run scan'));
  }

  function openReviewAction(recordUuid: string, action: string) {
    setPendingReviewAction({ recordUuid, action });
    setRedactedDescription('');
  }

  async function reviewAction() {
    if (!pendingReviewAction) {
      return;
    }
    const { recordUuid, action } = pendingReviewAction;
    const body = action === 'redact' ? { redacted_description: redactedDescription } : {};
    HttpService.axiosClient
      .post(`/spam-detection/review/${recordUuid}/${action}`, body)
      .then(() => {
        showMessage(`${action} completed`);
        setPendingReviewAction(null);
        loadReview();
      })
      .catch((error) => showMessage(error.response?.data?.message || `Unable to ${action}`));
  }

  if (!UserService.hasRealmRole(SPAM_DETECTION_ROLE)) {
    return null;
  }

  return (
    <PageSection>
      <Modal
        isOpen={message !== ''}
        variant={ModalVariant.small}
        aria-label="spam detection feedback"
        showClose
        onClose={() => setMessage('')}
      >
        <span>{message}</span>
      </Modal>
      <Modal
        isOpen={pendingReviewAction !== null}
        variant={ModalVariant.small}
        title={`${pendingReviewAction?.action || ''} repository`}
        onClose={() => setPendingReviewAction(null)}
        actions={[
          <Button
            key="confirm"
            variant={pendingReviewAction?.action === 'redact' ? 'danger' : 'primary'}
            onClick={reviewAction}
            isDisabled={pendingReviewAction?.action === 'redact' && redactedDescription.length === 0}
          >
            Confirm
          </Button>,
          <Button key="cancel" variant="link" onClick={() => setPendingReviewAction(null)}>
            Cancel
          </Button>,
        ]}
      >
        {pendingReviewAction?.action === 'redact' && (
          <Form>
            <FormGroup label="Redacted description" fieldId="redacted-description">
              <TextArea
                id="redacted-description"
                value={redactedDescription}
                onChange={(value) => setRedactedDescription(value)}
              />
            </FormGroup>
          </Form>
        )}
      </Modal>
      {loading && <Spinner role="spam-detection-loading" isSVG />}
      <Tabs activeKey={activeTab} onSelect={(_, key) => setActiveTab(key as number)}>
        <Tab eventKey={0} title={<TabTitleText>Classifier</TabTitleText>}>
          <Grid hasGutter>
            <GridItem span={5}>
              <Card>
                <CardTitle>Create classifier</CardTitle>
                <CardBody>
                  <Form>
                    <FormGroup label="Name" fieldId="classifier-name">
                      <TextInput
                        id="classifier-name"
                        value={classifierName}
                        onChange={(value) => setClassifierName(value)}
                      />
                    </FormGroup>
                    <Button variant="primary" onClick={createClassifier} isDisabled={!classifierName}>
                      Create
                    </Button>
                  </Form>
                </CardBody>
              </Card>
            </GridItem>
            <GridItem span={7}>
              <Card>
                <CardTitle>Training</CardTitle>
                <CardBody>
                  <Form>
                    <FormGroup label="Classifier UUID" fieldId="classifier-uuid">
                      <TextInput
                        id="classifier-uuid"
                        value={selectedClassifier}
                        onChange={(value) => setSelectedClassifier(value)}
                      />
                    </FormGroup>
                    <FormGroup label="Label" fieldId="training-label">
                      <TextInput
                        id="training-label"
                        value={trainingLabel}
                        onChange={(value) => setTrainingLabel(value)}
                      />
                    </FormGroup>
                    <FormGroup label="Text" fieldId="training-text">
                      <TextArea id="training-text" value={trainingText} onChange={(value) => setTrainingText(value)} />
                    </FormGroup>
                    <Button variant="secondary" onClick={addTrainingExample} isDisabled={!trainingText}>
                      Add example
                    </Button>{' '}
                    <Button variant="primary" onClick={trainClassifier} isDisabled={!selectedClassifier}>
                      Train artifact
                    </Button>{' '}
                    <Button variant="secondary" onClick={exportArtifact} isDisabled={!selectedClassifier}>
                      Export artifact
                    </Button>
                    <FormGroup label="Build output path" fieldId="export-output-path">
                      <TextInput
                        id="export-output-path"
                        value={exportOutputPath}
                        onChange={(value) => setExportOutputPath(value)}
                      />
                    </FormGroup>
                    <FormGroup label="Seed CSV path" fieldId="seed-csv-path">
                      <TextInput id="seed-csv-path" value={csvPath} onChange={(value) => setCsvPath(value)} />
                    </FormGroup>
                    <Button variant="secondary" onClick={importCsv} isDisabled={!csvPath || !selectedClassifier}>
                      Import CSV
                    </Button>
                  </Form>
                </CardBody>
              </Card>
            </GridItem>
          </Grid>
          <SimpleTable
            columns={['Name', 'Enabled', 'Artifact', 'SHA256']}
            rows={classifiers.map((item) => [
              item.name,
              item.enabled ? 'yes' : 'no',
              item.artifact_version || '',
              item.artifact_sha256 || '',
            ])}
          />
        </Tab>
        <Tab eventKey={1} title={<TabTitleText>Policy</TabTitleText>}>
          <Card>
            <CardTitle>Policy</CardTitle>
            <CardBody>
              <Form>
                <FormGroup label="Scan threshold" fieldId="scan-threshold">
                  <TextInput
                    id="scan-threshold"
                    value={String(policy.scan_threshold || '')}
                    onChange={(value) => setPolicy({ ...policy, scan_threshold: Number(value) })}
                  />
                </FormGroup>
                <FormGroup label="Ingress threshold" fieldId="ingress-threshold">
                  <TextInput
                    id="ingress-threshold"
                    value={String(policy.ingress_threshold || '')}
                    onChange={(value) => setPolicy({ ...policy, ingress_threshold: Number(value) })}
                  />
                </FormGroup>
                <Checkbox
                  id="include-private"
                  label="Include private repositories"
                  isChecked={Boolean(policy.include_private)}
                  onChange={(checked) => setPolicy({ ...policy, include_private: checked })}
                />
                <Checkbox
                  id="scan-dry-run"
                  label="Dry-run scans"
                  isChecked={Boolean(policy.scan_dry_run)}
                  onChange={(checked) => setPolicy({ ...policy, scan_dry_run: checked })}
                />
                <Checkbox
                  id="rescan-terminal-records"
                  label="Rescan unchanged terminal review records"
                  isChecked={Boolean(policy.rescan_terminal_records)}
                  onChange={(checked) => setPolicy({ ...policy, rescan_terminal_records: checked })}
                />
                <FormGroup label="Max repositories" fieldId="max-repos">
                  <TextInput
                    id="max-repos"
                    value={String(policy.max_repos || '')}
                    onChange={(value) => setPolicy({ ...policy, max_repos: Number(value) })}
                  />
                </FormGroup>
                <FormGroup label="Batch size" fieldId="batch-size">
                  <TextInput
                    id="batch-size"
                    value={String(policy.batch_size || '')}
                    onChange={(value) => setPolicy({ ...policy, batch_size: Number(value) })}
                  />
                </FormGroup>
                <FormGroup label="Quarantine description" fieldId="quarantine-description">
                  <TextArea
                    id="quarantine-description"
                    value={policy.quarantine_description || ''}
                    onChange={(value) => setPolicy({ ...policy, quarantine_description: value })}
                  />
                </FormGroup>
                <Button variant="primary" onClick={savePolicy}>
                  Save policy
                </Button>
              </Form>
            </CardBody>
          </Card>
        </Tab>
        <Tab eventKey={2} title={<TabTitleText>Preview</TabTitleText>}>
          <Button variant="primary" onClick={runPreview}>
            Preview
          </Button>
          {preview && (
            <Alert
              isInline
              title={`${preview.repos_matched} matches from ${preview.repos_scanned} repositories scanned`}
              variant="info"
            />
          )}
          <SimpleTable
            columns={['Repository', 'Visibility', 'Score', 'Hard filters', 'Description']}
            rows={(preview?.matches || []).map((item) => [
              `${item.namespace_name}/${item.repository_name}`,
              item.visibility,
              item.classifier_score.toFixed(4),
              formatHardFilters(item.hard_filter_results),
              item.description_excerpt,
            ])}
          />
        </Tab>
        <Tab eventKey={3} title={<TabTitleText>Runs</TabTitleText>}>
          <Button variant="primary" onClick={() => runScan(true)}>
            Run dry scan
          </Button>{' '}
          {canRemediate && (
            <Button variant="secondary" onClick={() => runScan(false)}>
              Run review scan
            </Button>
          )}
          <SimpleTable
            columns={['Run', 'Status', 'Dry run', 'Scanned', 'Matched', 'Flagged', 'Terminal skips']}
            rows={runs.map((item) => [
              item.uuid,
              item.status,
              item.dry_run ? 'yes' : 'no',
              item.repos_scanned,
              item.repos_matched,
              item.repos_flagged,
              item.repos_skipped_terminal || 0,
            ])}
          />
        </Tab>
        <Tab eventKey={4} title={<TabTitleText>Review</TabTitleText>}>
          <SimpleTable
            columns={['Repository', 'Status', 'Score', 'Actions']}
            rows={records.map((item) => [
              `${item.namespace_name}/${item.repository_name}`,
              item.status,
              item.classifier_score.toFixed(4),
              canRemediate ? (
                <span>
                  {item.status === 'flagged' && (
                    <Button variant="secondary" onClick={() => openReviewAction(item.uuid, 'quarantine')}>
                      Quarantine
                    </Button>
                  )}{' '}
                  {item.status === 'quarantined' && (
                    <Button variant="secondary" onClick={() => openReviewAction(item.uuid, 'restore')}>
                      Restore
                    </Button>
                  )}{' '}
                  {item.status === 'quarantined' && (
                    <Button variant="danger" onClick={() => openReviewAction(item.uuid, 'redact')}>
                      Redact
                    </Button>
                  )}{' '}
                  <Button variant="link" onClick={() => openReviewAction(item.uuid, 'dismiss')}>
                    Dismiss
                  </Button>
                </span>
              ) : (
                ''
              ),
            ])}
          />
        </Tab>
      </Tabs>
    </PageSection>
  );
};

const SimpleTable = ({ columns, rows }: { columns: string[]; rows: any[][] }) => (
  <table className="pf-c-table pf-m-grid-md" role="grid">
    <thead>
      <tr>
        {columns.map((column) => (
          <th key={column}>{column}</th>
        ))}
      </tr>
    </thead>
    <tbody>
      {rows.length === 0 ? (
        <tr>
          <td colSpan={columns.length}>No records</td>
        </tr>
      ) : (
        rows.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {row.map((cell, cellIndex) => (
              <td key={cellIndex}>{cell}</td>
            ))}
          </tr>
        ))
      )}
    </tbody>
  </table>
);
