import * as React from 'react';
import {
  Alert,
  Button,
  Card,
  CardBody,
  CardTitle,
  Form,
  FormGroup,
  FormSelect,
  FormSelectOption,
  Modal,
  ModalVariant,
  PageSection,
  Spinner,
  Split,
  SplitItem,
  Tab,
  Tabs,
  TabTitleText,
  TextInput,
  Title,
} from '@patternfly/react-core';
import { useState, useEffect } from 'react';
import HttpService from 'src/services/HttpService';
import { getErrorMessage } from '@app/utils/utils';

type SpamRule = {
  uuid: string;
  name: string;
  rule_type: string;
  pattern: string | null;
  config: Record<string, unknown>;
  confidence_score: number;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
};

type FlaggedRepo = {
  uuid: string;
  namespace_name: string;
  repository_name: string;
  status: string;
  original_description: string | null;
  matched_rules: Array<{
    rule_uuid: string;
    rule_name: string;
    rule_type: string;
    confidence: number;
  }>;
  total_confidence_score: number;
  is_empty: boolean;
  scan_id: string | null;
  actioned_by: string | null;
  actioned_at: string | null;
  created_at: string | null;
};

const RULE_TYPES = [
  { value: 'keyword', label: 'Keyword Match' },
  { value: 'url_pattern', label: 'URL Pattern (Regex)' },
  { value: 'repo_name_pattern', label: 'Repository Name Pattern (Regex)' },
  { value: 'empty_repo', label: 'Empty Repository' },
  { value: 'account_age', label: 'Account Age' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'flagged', label: 'Flagged' },
  { value: 'quarantined', label: 'Quarantined' },
  { value: 'restored', label: 'Restored' },
  { value: 'dismissed', label: 'Dismissed' },
];

export const SpamDetection: React.FunctionComponent = () => {
  const [activeTab, setActiveTab] = useState<string | number>(0);

  // Rules state
  const [rules, setRules] = useState<SpamRule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState('');

  // Create rule state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newRuleName, setNewRuleName] = useState('');
  const [newRuleType, setNewRuleType] = useState('keyword');
  const [newRulePattern, setNewRulePattern] = useState('');
  const [newRuleConfidence, setNewRuleConfidence] = useState(50);

  // Flagged repos state
  const [flaggedRepos, setFlaggedRepos] = useState<FlaggedRepo[]>([]);
  const [reposLoading, setReposLoading] = useState(false);
  const [reposError, setReposError] = useState('');
  const [statusFilter, setStatusFilter] = useState('flagged');

  // Detail modal
  const [selectedRepo, setSelectedRepo] = useState<FlaggedRepo | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);

  // Feedback
  const [feedback, setFeedback] = useState<{
    variant: 'success' | 'danger' | 'info';
    message: string;
    show: boolean;
  }>({ variant: 'success', message: '', show: false });

  const loadRules = () => {
    setRulesLoading(true);
    setRulesError('');
    HttpService.axiosClient
      .get('/spam/rules')
      .then((response) => {
        setRules(response.data.rules || []);
        setRulesLoading(false);
      })
      .catch((error) => {
        setRulesError(getErrorMessage(error));
        setRulesLoading(false);
      });
  };

  const loadFlaggedRepos = () => {
    setReposLoading(true);
    setReposError('');
    const params: Record<string, string | number> = { limit: 50 };
    if (statusFilter) params.status = statusFilter;
    HttpService.axiosClient
      .get('/spam/flagged', { params })
      .then((response) => {
        setFlaggedRepos(response.data.flagged_repos || []);
        setReposLoading(false);
      })
      .catch((error) => {
        setReposError(getErrorMessage(error));
        setReposLoading(false);
      });
  };

  useEffect(() => {
    loadRules();
  }, []);

  useEffect(() => {
    loadFlaggedRepos();
  }, [statusFilter]);

  const createRule = () => {
    HttpService.axiosClient
      .post('/spam/rules', {
        name: newRuleName,
        rule_type: newRuleType,
        pattern: newRulePattern || undefined,
        confidence_score: newRuleConfidence,
      })
      .then(() => {
        setShowCreateModal(false);
        setNewRuleName('');
        setNewRulePattern('');
        setNewRuleConfidence(50);
        setFeedback({ variant: 'success', message: 'Rule created', show: true });
        loadRules();
      })
      .catch((error) => {
        setFeedback({ variant: 'danger', message: getErrorMessage(error), show: true });
      });
  };

  const deleteRule = (uuid: string) => {
    HttpService.axiosClient
      .delete(`/spam/rules/${uuid}`)
      .then(() => {
        setFeedback({ variant: 'success', message: 'Rule deleted', show: true });
        loadRules();
      })
      .catch((error) => {
        setFeedback({ variant: 'danger', message: getErrorMessage(error), show: true });
      });
  };

  const toggleRule = (rule: SpamRule) => {
    HttpService.axiosClient
      .put(`/spam/rules/${rule.uuid}`, { enabled: !rule.enabled })
      .then(() => {
        loadRules();
      })
      .catch((error) => {
        setFeedback({ variant: 'danger', message: getErrorMessage(error), show: true });
      });
  };

  const actionRepo = (uuid: string, action: string) => {
    HttpService.axiosClient
      .post(`/spam/flagged/${uuid}/${action}`)
      .then(() => {
        setFeedback({ variant: 'success', message: `Repository ${action}d`, show: true });
        loadFlaggedRepos();
      })
      .catch((error) => {
        setFeedback({ variant: 'danger', message: getErrorMessage(error), show: true });
      });
  };

  return (
    <PageSection>
      <Title headingLevel="h1" style={{ marginBottom: '1rem' }}>
        Spam Detection
      </Title>

      {feedback.show && (
        <Alert
          variant={feedback.variant}
          title={feedback.message}
          isInline
          actionClose={
            <Button variant="plain" onClick={() => setFeedback({ ...feedback, show: false })}>
              &times;
            </Button>
          }
          style={{ marginBottom: '1rem' }}
        />
      )}

      <Tabs activeKey={activeTab} onSelect={(_e, key) => setActiveTab(key)}>
        <Tab eventKey={0} title={<TabTitleText>Flagged Repositories</TabTitleText>}>
          <Card style={{ marginTop: '1rem' }}>
            <CardBody>
              <Split hasGutter style={{ marginBottom: '1rem' }}>
                <SplitItem>
                  <FormSelect
                    value={statusFilter}
                    onChange={(_e, val) => setStatusFilter(val)}
                    style={{ width: '200px' }}
                    aria-label="Filter by status"
                  >
                    {STATUS_OPTIONS.map((opt) => (
                      <FormSelectOption key={opt.value} value={opt.value} label={opt.label} />
                    ))}
                  </FormSelect>
                </SplitItem>
                <SplitItem>
                  <Button variant="secondary" onClick={loadFlaggedRepos}>
                    Refresh
                  </Button>
                </SplitItem>
              </Split>

              {reposLoading ? (
                <Spinner size="lg" />
              ) : reposError ? (
                <Alert variant="danger" title={reposError} isInline />
              ) : flaggedRepos.length === 0 ? (
                <p>No flagged repositories found.</p>
              ) : (
                <table className="pf-v5-c-table pf-m-compact" role="grid">
                  <thead>
                    <tr>
                      <th>Repository</th>
                      <th>Status</th>
                      <th>Confidence</th>
                      <th>Rules</th>
                      <th>Empty</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flaggedRepos.map((repo) => (
                      <tr key={repo.uuid}>
                        <td>
                          <Button
                            variant="link"
                            isInline
                            onClick={() => {
                              setSelectedRepo(repo);
                              setShowDetailModal(true);
                            }}
                          >
                            {repo.namespace_name}/{repo.repository_name}
                          </Button>
                        </td>
                        <td>{repo.status}</td>
                        <td>{repo.total_confidence_score}</td>
                        <td>{repo.matched_rules?.length || 0}</td>
                        <td>{repo.is_empty ? 'Yes' : 'No'}</td>
                        <td>
                          {repo.status === 'flagged' && (
                            <>
                              <Button
                                variant="danger"
                                isSmall
                                onClick={() => actionRepo(repo.uuid, 'quarantine')}
                                style={{ marginRight: '0.5rem' }}
                              >
                                Quarantine
                              </Button>
                              <Button
                                variant="secondary"
                                isSmall
                                onClick={() => actionRepo(repo.uuid, 'dismiss')}
                              >
                                Dismiss
                              </Button>
                            </>
                          )}
                          {repo.status === 'quarantined' && (
                            <Button
                              variant="secondary"
                              isSmall
                              onClick={() => actionRepo(repo.uuid, 'restore')}
                            >
                              Restore
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardBody>
          </Card>
        </Tab>

        <Tab eventKey={1} title={<TabTitleText>Rules</TabTitleText>}>
          <Card style={{ marginTop: '1rem' }}>
            <CardBody>
              <Button
                variant="primary"
                onClick={() => setShowCreateModal(true)}
                style={{ marginBottom: '1rem' }}
              >
                Create Rule
              </Button>

              {rulesLoading ? (
                <Spinner size="lg" />
              ) : rulesError ? (
                <Alert variant="danger" title={rulesError} isInline />
              ) : rules.length === 0 ? (
                <p>No detection rules configured.</p>
              ) : (
                <table className="pf-v5-c-table pf-m-compact" role="grid">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Type</th>
                      <th>Pattern</th>
                      <th>Confidence</th>
                      <th>Enabled</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule) => (
                      <tr key={rule.uuid}>
                        <td>{rule.name}</td>
                        <td>
                          {RULE_TYPES.find((t) => t.value === rule.rule_type)?.label ||
                            rule.rule_type}
                        </td>
                        <td>{rule.pattern || '-'}</td>
                        <td>{rule.confidence_score}</td>
                        <td>{rule.enabled ? 'Yes' : 'No'}</td>
                        <td>
                          <Button
                            variant="secondary"
                            isSmall
                            onClick={() => toggleRule(rule)}
                            style={{ marginRight: '0.5rem' }}
                          >
                            {rule.enabled ? 'Disable' : 'Enable'}
                          </Button>
                          <Button
                            variant="danger"
                            isSmall
                            onClick={() => deleteRule(rule.uuid)}
                          >
                            Delete
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardBody>
          </Card>
        </Tab>
      </Tabs>

      {/* Create Rule Modal */}
      <Modal
        variant={ModalVariant.medium}
        title="Create Detection Rule"
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        actions={[
          <Button key="create" variant="primary" onClick={createRule} isDisabled={!newRuleName}>
            Create
          </Button>,
          <Button key="cancel" variant="link" onClick={() => setShowCreateModal(false)}>
            Cancel
          </Button>,
        ]}
      >
        <Form>
          <FormGroup label="Name" isRequired fieldId="rule-name">
            <TextInput
              id="rule-name"
              value={newRuleName}
              onChange={(_e, val) => setNewRuleName(val)}
              isRequired
            />
          </FormGroup>
          <FormGroup label="Rule Type" isRequired fieldId="rule-type">
            <FormSelect
              id="rule-type"
              value={newRuleType}
              onChange={(_e, val) => setNewRuleType(val)}
            >
              {RULE_TYPES.map((t) => (
                <FormSelectOption key={t.value} value={t.value} label={t.label} />
              ))}
            </FormSelect>
          </FormGroup>
          {newRuleType !== 'empty_repo' && newRuleType !== 'account_age' && (
            <FormGroup
              label="Pattern"
              fieldId="rule-pattern"
              helperText={
                newRuleType === 'keyword'
                  ? 'Comma-separated keywords'
                  : 'Regular expression'
              }
            >
              <TextInput
                id="rule-pattern"
                value={newRulePattern}
                onChange={(_e, val) => setNewRulePattern(val)}
              />
            </FormGroup>
          )}
          <FormGroup label="Confidence Score (0-100)" fieldId="rule-confidence">
            <TextInput
              id="rule-confidence"
              type="number"
              value={newRuleConfidence}
              onChange={(_e, val) => setNewRuleConfidence(parseInt(val) || 0)}
              min={0}
              max={100}
            />
          </FormGroup>
        </Form>
      </Modal>

      {/* Detail Modal */}
      <Modal
        variant={ModalVariant.large}
        title={
          selectedRepo
            ? `${selectedRepo.namespace_name}/${selectedRepo.repository_name}`
            : ''
        }
        isOpen={showDetailModal}
        onClose={() => setShowDetailModal(false)}
        actions={[
          <Button key="close" variant="link" onClick={() => setShowDetailModal(false)}>
            Close
          </Button>,
        ]}
      >
        {selectedRepo && (
          <div>
            <p>
              <strong>Status:</strong> {selectedRepo.status}
            </p>
            <p>
              <strong>Confidence Score:</strong> {selectedRepo.total_confidence_score}
            </p>
            <p>
              <strong>Empty:</strong> {selectedRepo.is_empty ? 'Yes' : 'No'}
            </p>
            <p>
              <strong>Original Description:</strong>{' '}
              {selectedRepo.original_description || '(none)'}
            </p>
            <p>
              <strong>Matched Rules:</strong>
            </p>
            <ul>
              {selectedRepo.matched_rules?.map((r, i) => (
                <li key={i}>
                  {r.rule_name} ({r.rule_type}) - confidence: {r.confidence}
                </li>
              ))}
            </ul>
            {selectedRepo.actioned_by && (
              <p>
                <strong>Actioned By:</strong> {selectedRepo.actioned_by} at{' '}
                {selectedRepo.actioned_at}
              </p>
            )}
          </div>
        )}
      </Modal>
    </PageSection>
  );
};
