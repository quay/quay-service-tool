import * as React from 'react';
import {
  ActionGroup,
  Banner, BannerProps, Button,
  Card,
  CardBody,
  CardTitle,
  Form,
  FormGroup,
  FormSelect,
  FormSelectOption,
  PageSection,
  TextInput
} from '@patternfly/react-core';
import ReactMarkdown from 'react-markdown';
import { useState } from 'react';

type Props = {

};
export const UserUtils : React.FunctionComponent = (props: Props) => {

  const [currentUsername, setCurrentUsername] = useState('');
  const [newUsername, setNewUsername] = useState('');

  return (
    <div>
      <PageSection>

        {/* Rename User*/}
        <Card>
          <CardTitle className={"text-uppercase"}> Rename User </CardTitle>
          <CardBody>
            <Form>
              <FormGroup label="Current Username" fieldId="current-user" isRequired>
                <TextInput
                  isRequired
                  type="text"
                  id="current-user"
                  name="current-user"
                  value={currentUsername}
                  onChange={(value) => setCurrentUsername(value)}
                  placeholder="Current Username"
                />
              </FormGroup>

              <FormGroup label="New Username" fieldId="new-user" isRequired>
                <TextInput
                  isRequired
                  type="text"
                  id="new-user"
                  name="new-user"
                  value={newUsername}
                  onChange={(value) => setNewUsername(value)}
                  placeholder="New Username"
                />
              </FormGroup>

              <ActionGroup>
                <Button variant="primary">Update Username</Button>
              </ActionGroup>
            </Form>
          </CardBody>
        </Card>

      </PageSection>
        {/* Email invoice */}

  <PageSection>
    <Card>
          <CardTitle className={"text-uppercase"}> Email Invoice </CardTitle>
          <CardBody>
            <Form>
              <FormGroup label="Invoice ID" fieldId="invoice-id" isRequired>
                <TextInput
                  isRequired
                  type="text"
                  id="invoice-id"
                  name="invoice-id"
                  value={currentUsername}
                  onChange={(value) => setCurrentUsername(value)}
                  placeholder="Invoice ID"
                />
              </FormGroup>

              <ActionGroup>
                <Button variant="primary">Email Invoice</Button>
              </ActionGroup>
            </Form>
          </CardBody>
        </Card>

  </PageSection>
  {/* Send Confirmation Email */}
    <PageSection>
        <Card>
          <CardTitle className={"text-uppercase"}> Send Confirmation Email </CardTitle>
          <CardBody>
            <Form>
              <FormGroup label="Username" fieldId="confirm-email-user" isRequired>
                <TextInput
                  isRequired
                  type="text"
                  id="confirm-email-user"
                  name="confirm-email-user"
                  value={currentUsername}
                  onChange={(value) => setCurrentUsername(value)}
                  placeholder="Username"
                />
              </FormGroup>

              <ActionGroup>
                <Button variant="primary">Send Confirmation Email</Button>
              </ActionGroup>
            </Form>
          </CardBody>
        </Card>
      </PageSection>
    </div>
  );
};
