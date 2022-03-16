import * as React from 'react';
import {
    ActionGroup,
    Alert,
    AlertActionCloseButton,
    Button,
    Card,
    CardBody,
    CardTitle,
    Form,
    FormGroup,
    Modal,
    ModalVariant,
    PageSection,
    TextInput,
  } from '@patternfly/react-core';
import HttpService from "../../../services/HttpService";
import { useState } from 'react';
import { getErrorMessage } from '@app/utils/utils';

type Props = {

};

type Alert = {
    variant: "success" | "danger" | "default" | "warning" | "info" | undefined;
    show: boolean;
    title: string;
}

export const DeleteUser: React.FunctionComponent = (props: Props) => {
    const [alert, setAlert] = useState<Alert>({
        variant: 'success',
        show: false,
        title: ''
    });
    const [username, setUsername] = useState('');
    const [showModal, setShowModal] = useState(false);

    async function promptDeleteUser(){
        if(username.length == 0){
            setAlert({ variant: 'danger', show: true, title: 'Please enter a username' });
            return;
        }
        HttpService.axiosClient.get(`/user/${username}`)
            .then(function(response){
                if(!response.data.enabled){
                    setAlert({variant: "danger", show: true, title: `User ${username} is already deleted`});
                } else {
                    setShowModal(true);
                }
            })
            .catch((error) => {
                const errMessage = error.response.status == 404 ? `User ${username} does not exist` : getErrorMessage(error);
                setAlert({variant: "danger", show: true, title: errMessage})
            });
    }

    async function deleteUser(){
        HttpService.axiosClient.delete(`/user/${username}`)
          .then(function(response){
            setShowModal(false);
            setAlert({variant: "success", show: true, title: `User ${response.data.user} deleted`});
          })
          .catch((error) => {
            setShowModal(false);
            setAlert({variant: "danger", show: true, title: getErrorMessage(error)})
        });
    }

    let modal: JSX.Element | null = null;
    if(showModal){
        const title = `Delete user ${username}?`;
        modal = (
            <Modal
            title={title}
            isOpen={showModal}
            variant={ModalVariant.small}
            aria-label="feedback modal"
            showClose={true}
            onClose={() => setShowModal(false)}
            aria-describedby="no-header-example"
            >
                <Button id="delete-user-confirm" variant="primary" onClick={deleteUser}>Delete User</Button>
            </Modal>
        );
    }
    return (
    <PageSection>
        {modal}
        <Card>
          <CardTitle className={"text-uppercase"}> Delete User </CardTitle>
          {alert.show && <Alert id="delete-user-alert" isInline actionClose={<AlertActionCloseButton onClose={() => setAlert({ variant: 'success', show: false, title: ''})} />} variant={alert.variant} title={alert.title} />}
          <CardBody>
            <Form id="enable-user-form">
              <FormGroup label="Username" fieldId="delete-username" isRequired>
                <TextInput
                  isRequired
                  type="text"
                  id="delete-username"
                  name="delete-username"
                  value={username}
                  onChange={(value) => setUsername(value)}
                  placeholder="Username"
                />
              </FormGroup>

              <ActionGroup>
                <Button id="delete-user-submit" variant="primary" onClick={promptDeleteUser}>Delete User</Button>
              </ActionGroup>
            </Form>
          </CardBody>
        </Card>
      </PageSection>
    );
}
