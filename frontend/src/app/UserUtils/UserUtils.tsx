import * as React from 'react';
import {
  ActionGroup,
  Button,
  Card,
  CardBody,
  CardTitle,
  Form,
  FormGroup,
  Modal,
  ModalVariant,
  PageSection,
  TextInput
} from '@patternfly/react-core';
import { useState } from 'react';
import axios from 'axios';

type Props = {

};
export const UserUtils : React.FunctionComponent = (props: Props) => {

  const [currentUsername, setCurrentUsername] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [message, setMessage] = useState('');

  async function onRenameUser() {
    if (currentUsername && newUsername) {
       axios.put('/username', {
        currentUsername,
        newUsername
      }) 
      .then(function (response) {
        setMessage('Succeeded');
        setIsModalOpen(true);
      })
      .catch(function (error) {
        setMessage(error.response.data.message);
        setIsModalOpen(true);
      });
    }
  }

  return (
    <div>
      <PageSection>
        
        <Modal
          isOpen={isModalOpen}
          variant={ModalVariant.small}
          aria-label="feedback modal"
          showClose={true}
          aria-describedby="no-header-example"
          onClose={() => { setIsModalOpen(!isModalOpen)} }
        >
          <span>{message}</span>
      </Modal>
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
                <Button variant="primary" onClick={onRenameUser}>Update Username</Button>
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
