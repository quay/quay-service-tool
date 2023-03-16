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

export const DisableUser: React.FunctionComponent = (props: Props) => {
    const [alert, setAlert] = useState<Alert>({
        variant: 'success',
        show: false,
        title: ''
    });
    const [username, setUsername] = useState('');
    const [showModal, setShowModal] = useState(false);

    async function promptDisableUser(){
        if(username.length == 0){
            setAlert({ variant: 'danger', show: true, title: 'Please enter a username' });
            return;
        }
        HttpService.axiosClient.get(`/user/${username}`)
            .then(function(response){
                if(!response.data.enabled){
                    setAlert({variant: "danger", show: true, title: `User ${username} is already disabled`});
                } else {
                    setShowModal(true);
                }
            })
            .catch((error) => { 
                let errMessage = error.response.status == 404 ? `User ${username} does not exist` : getErrorMessage(error);
                setAlert({variant: "danger", show: true, title: errMessage}) 
            });
    }

    async function disableUser(){
        HttpService.axiosClient.put(`/user/${username}?enable=false`)
          .then(function(response){
            setShowModal(false);
            setAlert({variant: "success", show: true, title: `User ${response.data.user} disabled`});
          })
          .catch((error) => { 
            setShowModal(false);  
            setAlert({variant: "danger", show: true, title: getErrorMessage(error)}) 
        });
    }

    let modal: JSX.Element | null = null;
    if(showModal){
        let title = `Disable user ${username}?`;
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
                <Button id="disable-user-confirm" variant="primary" onClick={disableUser}>Disable User</Button>
            </Modal>
        );
    }
    return (
    <PageSection>
        {modal}
        <Card>
          <CardTitle className={"text-uppercase"}> Disable User </CardTitle>
          {alert.show && <Alert id="disable-user-alert" isInline actionClose={<AlertActionCloseButton onClose={() => setAlert({ variant: 'success', show: false, title: ''})} />} variant={alert.variant} title={alert.title} />}
          <CardBody>
            <Form id="enable-user-form">
              <FormGroup label="Username" fieldId="disable-username" isRequired>
                <TextInput
                  isRequired
                  type="text"
                  id="disable-username"
                  name="disable-username"
                  value={username}
                  onChange={(value) => setUsername(value)}
                  placeholder="Username"
                />
              </FormGroup>

              <ActionGroup>
                <Button id="disable-user-submit" variant="primary" onClick={promptDisableUser}>Disable User</Button>
              </ActionGroup>
            </Form>
          </CardBody>
        </Card>
      </PageSection>
    );
}
