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
  Title,
} from '@patternfly/react-core';
import { useEffect, useState } from 'react';
import HttpService from 'src/services/HttpService';
import UserService from 'src/services/UserService';
import './SpamDetection.css';

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
  const [terminalRecords, setTerminalRecords] = useState<any[]>([]);
  const [actions, setActions] = useState<any[]>([]);
  const [preview, setPreview] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [classifierName, setClassifierName] = useState('');
  const [trainingText, setTrainingText] = useState('');
  const [trainingLabel, setTrainingLabel] = useState('spam');
  const [csvPath, setCsvPath] = useState('');
  const [selectedClassifier, setSelectedClassifier] = useState('');
  const [pendingReviewAction, setPendingReviewAction] = useState<{ recordUuid: string; action: string } | null>(null);
  const [redactedDescription, setRedactedDescription] = useState('');
  const [reviewReason, setReviewReason] = useState('');

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
    await Promise.all([loadClassifiers(), loadPolicy(), loadRuns(), loadReview(), loadAudit()]);
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
    return Promise.all([
      HttpService.axiosClient.get('/spam-detection/review').then((response) => {
        setRecords(response.data.records || []);
      }),
      HttpService.axiosClient.get('/spam-detection/review?status=restored&status=dismissed').then((response) => {
        setTerminalRecords(response.data.records || []);
      }),
    ]);
  }

  async function loadAudit() {
    return HttpService.axiosClient.get('/spam-detection/audit').then((response) => {
      setActions(response.data.actions || []);
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
      .post(`/spam-detection/classifiers/${selectedClassifier}/export-artifact`, {})
      .then(async (response) => {
        const artifact = await HttpService.axiosClient.get(
          `/spam-detection/classifiers/${selectedClassifier}/artifact`,
          { responseType: 'blob' }
        );
        const url = window.URL.createObjectURL(artifact.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = `quay-spam-classifier-${response.data.classifier.artifact_version}.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
        showMessage(`Artifact ${response.data.classifier.artifact_version} downloaded`);
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
    const hyperlink = filters?.description_hyperlink;
    return [
      repositoryEmpty ? `empty:${repositoryEmpty.matched ? 'yes' : 'no'}` : null,
      visibility ? `visibility:${visibility.value || 'unknown'}` : null,
      hyperlink ? `hyperlink:${hyperlink.matched ? 'yes' : 'no'}` : null,
    ]
      .filter(Boolean)
      .join(', ');
  }

  async function runScan(dryRun: boolean) {
    const maxRepos = Number(policy.max_repos) > 0 ? Number(policy.max_repos) : 0;
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
    setReviewReason('');
  }

  async function reviewAction() {
    if (!pendingReviewAction) {
      return;
    }
    const { recordUuid, action } = pendingReviewAction;
    const classifyLabel = action.startsWith('classify-') ? action.substring('classify-'.length) : null;
    const endpoint = classifyLabel ? 'classify' : action;
    const body =
      action === 'redact'
        ? { redacted_description: redactedDescription }
        : action === 'reopen'
        ? { reason: reviewReason.trim() }
        : classifyLabel
        ? { label: classifyLabel }
        : {};
    HttpService.axiosClient
      .post(`/spam-detection/review/${recordUuid}/${endpoint}`, body)
      .then(() => {
        showMessage(classifyLabel ? `Match labeled ${classifyLabel}` : `${action} completed`);
        setPendingReviewAction(null);
        loadReview();
        loadAudit();
      })
      .catch((error) => showMessage(error.response?.data?.message || `Unable to ${action}`));
  }

  if (!UserService.hasRealmRole(SPAM_DETECTION_ROLE)) {
    return null;
  }

  return (
    <PageSection className="spam-detection-page">
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
            isDisabled={
              (pendingReviewAction?.action === 'redact' && redactedDescription.length === 0) ||
              (pendingReviewAction?.action === 'reopen' && reviewReason.trim().length === 0)
            }
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
        {pendingReviewAction?.action === 'reopen' && (
          <Form>
            <FormGroup label="Reason" fieldId="reopen-reason">
              <TextArea id="reopen-reason" value={reviewReason} onChange={(value) => setReviewReason(value)} />
            </FormGroup>
          </Form>
        )}
      </Modal>
      {loading && <Spinner role="spam-detection-loading" isSVG />}
      <div className="spam-detection-header">
        <Title headingLevel="h1" size="xl">
          Spam detection
        </Title>
      </div>
      <Tabs className="spam-detection-tabs" activeKey={activeTab} onSelect={(_, key) => setActiveTab(key as number)}>
        <Tab eventKey={0} title={<TabTitleText>Classifier</TabTitleText>}>
          <div className="spam-detection-tab-content">
            <Grid hasGutter className="spam-detection-card-grid">
              <GridItem sm={12} lg={5}>
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
                      <div className="spam-detection-button-row">
                        <Button variant="primary" onClick={createClassifier} isDisabled={!classifierName}>
                          Create
                        </Button>
                      </div>
                    </Form>
                  </CardBody>
                </Card>
              </GridItem>
              <GridItem sm={12} lg={7}>
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
                        <TextArea
                          id="training-text"
                          value={trainingText}
                          onChange={(value) => setTrainingText(value)}
                        />
                      </FormGroup>
                      <div className="spam-detection-button-row">
                        <Button variant="secondary" onClick={addTrainingExample} isDisabled={!trainingText}>
                          Add example
                        </Button>
                        <Button variant="primary" onClick={trainClassifier} isDisabled={!selectedClassifier}>
                          Train artifact
                        </Button>
                        <Button variant="secondary" onClick={exportArtifact} isDisabled={!selectedClassifier}>
                          Export artifact
                        </Button>
                      </div>
                      <FormGroup label="Seed CSV path" fieldId="seed-csv-path">
                        <TextInput id="seed-csv-path" value={csvPath} onChange={(value) => setCsvPath(value)} />
                      </FormGroup>
                      <div className="spam-detection-button-row">
                        <Button variant="secondary" onClick={importCsv} isDisabled={!csvPath || !selectedClassifier}>
                          Import CSV
                        </Button>
                      </div>
                    </Form>
                  </CardBody>
                </Card>
              </GridItem>
            </Grid>
            <SimpleTable
              ariaLabel="Classifiers"
              variant="classifiers"
              columns={['Name', 'Enabled', 'Artifact', 'SHA256']}
              rows={classifiers.map((item) => [
                item.name,
                item.enabled ? 'yes' : 'no',
                <span key="artifact" className="spam-detection-monospace">
                  {item.artifact_version || ''}
                </span>,
                <span key="sha256" className="spam-detection-monospace">
                  {item.artifact_sha256 || ''}
                </span>,
              ])}
            />
          </div>
        </Tab>
        <Tab eventKey={1} title={<TabTitleText>Policy</TabTitleText>}>
          <div className="spam-detection-tab-content">
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
                      value={Number(policy.max_repos) > 0 ? String(policy.max_repos) : ''}
                      onChange={(value) => setPolicy({ ...policy, max_repos: Number(value) })}
                      isDisabled={Number(policy.max_repos) === 0}
                    />
                  </FormGroup>
                  <Checkbox
                    id="scan-all-repositories"
                    label="Scan all repositories"
                    isChecked={Number(policy.max_repos) === 0}
                    onChange={(checked) =>
                      setPolicy({ ...policy, max_repos: checked ? 0 : Number(policy.max_repos) || 1000 })
                    }
                  />
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
                  <div className="spam-detection-button-row">
                    <Button variant="primary" onClick={savePolicy}>
                      Save policy
                    </Button>
                  </div>
                </Form>
              </CardBody>
            </Card>
          </div>
        </Tab>
        <Tab eventKey={2} title={<TabTitleText>Preview</TabTitleText>}>
          <div className="spam-detection-tab-content">
            <div className="spam-detection-button-row">
              <Button variant="primary" onClick={runPreview}>
                Preview
              </Button>
            </div>
            {preview && (
              <Alert
                isInline
                title={`${preview.repos_matched} matches from ${preview.repos_scanned} repositories scanned`}
                variant="info"
              />
            )}
            <SimpleTable
              ariaLabel="Preview matches"
              variant="preview"
              columns={['Repository', 'Visibility', 'Score', 'Hard filters', 'Description']}
              rows={(preview?.matches || []).map((item) => [
                `${item.namespace_name}/${item.repository_name}`,
                item.visibility,
                <span key="score" className="spam-detection-score">
                  {item.classifier_score.toFixed(4)}
                </span>,
                formatHardFilters(item.hard_filter_results),
                item.description_excerpt,
              ])}
            />
          </div>
        </Tab>
        <Tab eventKey={3} title={<TabTitleText>Runs</TabTitleText>}>
          <div className="spam-detection-tab-content">
            <div className="spam-detection-button-row">
              <Button variant="primary" onClick={() => runScan(true)}>
                Run dry scan
              </Button>
              {canRemediate && (
                <Button variant="secondary" onClick={() => runScan(false)}>
                  Run review scan
                </Button>
              )}
            </div>
            <SimpleTable
              ariaLabel="Scan runs"
              variant="runs"
              columns={['Run', 'Status', 'Dry run', 'Scanned', 'Matched', 'Flagged', 'Terminal skips']}
              rows={runs.map((item) => [
                <span key="run" className="spam-detection-monospace">
                  {item.uuid}
                </span>,
                item.status,
                item.dry_run ? 'yes' : 'no',
                item.repos_scanned,
                item.repos_matched,
                item.repos_flagged,
                item.repos_skipped_terminal || 0,
              ])}
            />
          </div>
        </Tab>
        <Tab eventKey={4} title={<TabTitleText>Review</TabTitleText>}>
          <div className="spam-detection-tab-content">
            <Title headingLevel="h2" size="md" className="spam-detection-section-header">
              Active review
            </Title>
            <SimpleTable
              ariaLabel="Active review"
              variant="review"
              columns={['Repository', 'Status', 'Score', 'Actions']}
              rows={records.map((item) => [
                `${item.namespace_name}/${item.repository_name}`,
                item.status,
                <span key="score" className="spam-detection-score">
                  {item.classifier_score.toFixed(4)}
                </span>,
                canRemediate ? (
                  <span className="spam-detection-row-actions">
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
                    {['flagged', 'quarantined'].includes(item.status) && (
                      <Button variant="link" onClick={() => openReviewAction(item.uuid, 'dismiss')}>
                        Dismiss
                      </Button>
                    )}{' '}
                    <Button variant="link" onClick={() => openReviewAction(item.uuid, 'classify-spam')}>
                      Label spam
                    </Button>{' '}
                    <Button variant="link" onClick={() => openReviewAction(item.uuid, 'classify-ham')}>
                      Label ham
                    </Button>
                  </span>
                ) : (
                  ''
                ),
              ])}
            />
            <Title headingLevel="h2" size="md" className="spam-detection-section-header">
              Closed reviews
            </Title>
            <SimpleTable
              ariaLabel="Closed reviews"
              variant="review"
              columns={['Repository', 'Status', 'Score', 'Actions']}
              rows={terminalRecords.map((item) => [
                `${item.namespace_name}/${item.repository_name}`,
                item.status,
                <span key="score" className="spam-detection-score">
                  {item.classifier_score.toFixed(4)}
                </span>,
                canRemediate ? (
                  <Button variant="secondary" onClick={() => openReviewAction(item.uuid, 'reopen')}>
                    Reopen review
                  </Button>
                ) : (
                  ''
                ),
              ])}
            />
          </div>
        </Tab>
        <Tab eventKey={5} title={<TabTitleText>Audit</TabTitleText>}>
          <div className="spam-detection-tab-content">
            <SimpleTable
              ariaLabel="Audit history"
              variant="audit"
              columns={['Time', 'Repository', 'Action', 'Transition', 'Operator', 'Reason']}
              rows={actions.map((item) => [
                item.created_at,
                item.namespace_name && item.repository_name ? `${item.namespace_name}/${item.repository_name}` : '',
                item.action,
                [item.from_status, item.to_status].filter(Boolean).join(' -> '),
                item.operator || '',
                item.details_json?.reason || '',
              ])}
            />
          </div>
        </Tab>
      </Tabs>
    </PageSection>
  );
};

const SimpleTable = ({
  columns,
  rows,
  ariaLabel,
  variant,
}: {
  columns: string[];
  rows: any[][];
  ariaLabel: string;
  variant: string;
}) => (
  <div className="spam-detection-table-shell">
    <table className={`pf-c-table spam-detection-table spam-detection-table--${variant}`} aria-label={ariaLabel}>
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
            <td className="spam-detection-table__empty" colSpan={columns.length}>
              No records
            </td>
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
  </div>
);
