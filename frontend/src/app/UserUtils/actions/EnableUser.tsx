import * as React from 'react';
import { useState } from 'react';
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
import { getErrorMessage } from '@app/utils/utils';

type Props = {

};

type Alert = {
    variant: "success" | "danger" | "default" | "warning" | "info" | undefined;
    show: boolean;
    title: string;
}

export const EnableUser: React.FunctionComponent = (props: Props) => {
    const [username, setUsername] = useState('');
    const [alert, setAlert] = useState<Alert>({
        variant: 'success',
        show: false,
        title: ''
    });
    const [showModal, setShowModal] = useState(false);

    async function promptEnableUser(){
        if(username.length == 0){
            setAlert({ variant: 'danger', show: true, title: 'Please enter a username' });
            return;
        }
        HttpService.axiosClient.get(`/user/${username}`)
            .then(function(response){
                if(response.data.enabled){
                    setAlert({variant: "danger", show: true, title: `User ${username} is already enabled`});
                } else {
                    setShowModal(true);
                }
            })
            .catch((error) => {                 
                let errMessage = error.response.status == 404 ? `User ${username} does not exist` : getErrorMessage(error);
                setAlert({variant: "danger", show: true, title: errMessage})  
            });
    }

    async function enableUser(){
        HttpService.axiosClient.put(`/user/${username}?enable=true`)
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
            title={`Enable user ${username}?`}
            isOpen={showModal}
            variant={ModalVariant.small}
            aria-label="feedback modal"
            showClose={true}
            onClose={() => {setShowModal(false)}}
            aria-describedby="no-header-example"
            >
                <Button id="enable-user-confirm" variant="primary" onClick={enableUser}>Enable User</Button>
            </Modal>
        );
    }
    return (<>
        <PageSection>
            <Card>
                {modal}
                <CardTitle className={"text-uppercase"}> Enable User </CardTitle>
                {alert.show && <Alert id="enable-user-alert" isInline actionClose={<AlertActionCloseButton onClose={() => setAlert({ variant: 'success', show: false, title: ''})} />} variant={alert.variant} title={alert.title} />}
                <CardBody>
                    <Form id="enable-user-form">
                    <FormGroup label="Username" fieldId="enable-username" isRequired>
                        <TextInput
                        isRequired
                        type="text"
                        id="enable-username"
                        name="enable-username"
                        value={username}
                        onChange={(value) => setUsername(value)}
                        placeholder="Username"
                        />
                    </FormGroup>

                    <ActionGroup>
                        <Button id="enable-user-submit" variant="primary" onClick={promptEnableUser}>Enable User</Button>
                    </ActionGroup>
                    </Form>
                </CardBody>
            </Card>
        </PageSection>
    </>
    );
}
