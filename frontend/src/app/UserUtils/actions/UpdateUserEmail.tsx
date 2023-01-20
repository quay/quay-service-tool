import {
  ActionGroup, Alert, AlertActionCloseButton, Button,
  Card,
  CardBody,
  CardTitle,
  Form,
  FormGroup, Modal, ModalVariant,
  PageSection,
  TextInput
} from '@patternfly/react-core';
import { useState } from 'react';
import * as React from 'react';
import HttpService from '../../../services/HttpService';
import { getErrorMessage } from '@app/utils/utils';


type AlertType = {
  variant: "success" | "danger" | "default" | "warning" | "info" | undefined;
  show: boolean;
  title: string;
}

export const UpdateUserEmail: React.FunctionComponent = () => {
  const [username, setUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [alert, setAlert] = useState<AlertType>({
    variant: 'success',
    show: false,
    title: ''
  });


  async function updateEmail(){
    HttpService.axiosClient.put(`/user/email`, {username: username, newEmail: newEmail})
      .then(function(response){
        setShowModal(false);
        setAlert({variant: "success", show: true, title: `User ${response.data.user} enabled`});
      })
      .catch((error) => {
        setShowModal(false);
        setAlert({variant: "danger", show: true, title: getErrorMessage(error)})
      });
  }

  let modal: JSX.Element | null = null;
  if(showModal){
    modal = (
      <Modal
        title={`Update Email for user ${username} to ${newEmail}?`}
        isOpen={showModal}
        variant={ModalVariant.small}
        aria-label="feedback modal"
        showClose={true}
        onClose={() => {setShowModal(false)}}
        aria-describedby="no-header-example"
      >
        <Button id="update-email-confirm" variant="primary" onClick={updateEmail}>Update Email</Button>
      </Modal>
    );
  }

  return (<>
    <PageSection>
      <Card>
        {modal}
        <CardTitle className={"text-uppercase"}> Update User Email </CardTitle>
        {alert.show && <Alert id="update-email-alert" isInline actionClose={<AlertActionCloseButton onClose={() => setAlert({ variant: 'success', show: false, title: '' })} />} variant={alert.variant} title={alert.title} />}
        <CardBody>
          <Form id="update-email-form">
            <FormGroup label="Username" fieldId="update-email-username" isRequired>
              <TextInput
                isRequired
                type="text"
                id="update-email-username"
                name="update-email-username"
                value={username}
                onChange={(value) => setUsername(value)}
                placeholder="Username"
              />
            </FormGroup>

            <FormGroup label="Email" fieldId="update-email-newemail" isRequired>
              <TextInput
                isRequired
                type="text"
                id="update-email-newemail"
                name="update-email-newemail"
                value={newEmail}
                onChange={(value) => setNewEmail(value)}
                placeholder="New Email"
              />
            </FormGroup>

            <ActionGroup>
              <Button id="update-email-submit" variant="primary" onClick={() => setShowModal(true)}>Update Email</Button>
            </ActionGroup>
          </Form>
        </CardBody>
      </Card>
    </PageSection>
  </>
  );
}
