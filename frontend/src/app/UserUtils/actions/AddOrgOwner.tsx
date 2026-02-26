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

export const AddOrgOwner: React.FunctionComponent = (props: Props) => {
    const [username, setUsername] = useState('');
    const [orgName, setOrgName] = useState('');
    const [alert, setAlert] = useState<Alert>({
        variant: 'success',
        show: false,
        title: ''
    });
    const [showModal, setShowModal] = useState(false);

    async function promptAddOwner(){
        if(username.length == 0 || orgName.length == 0){
            setAlert({ variant: 'danger', show: true, title: 'Please enter both a username and an organization name' });
            return;
        }

        try {
            // Verify user exists and is not an org
            const userResponse = await HttpService.axiosClient.get(`/quayusername/${username}`);
            if(userResponse.data.is_organization){
                setAlert({variant: "danger", show: true, title: `Username ${username} refers to an organization, not a user`});
                return;
            }
        } catch(error) {
            if(error.response && error.response.status == 404){
                setAlert({variant: "danger", show: true, title: `User ${username} does not exist`});
            } else {
                setAlert({variant: "danger", show: true, title: getErrorMessage(error)});
            }
            return;
        }

        try {
            // Verify org exists and is an org
            const orgResponse = await HttpService.axiosClient.get(`/quayusername/${orgName}`);
            if(!orgResponse.data.is_organization){
                setAlert({variant: "danger", show: true, title: `${orgName} is not an organization`});
                return;
            }
        } catch(error) {
            if(error.response && error.response.status == 404){
                setAlert({variant: "danger", show: true, title: `Organization ${orgName} does not exist`});
            } else {
                setAlert({variant: "danger", show: true, title: getErrorMessage(error)});
            }
            return;
        }

        setShowModal(true);
    }

    async function addOwner(){
        HttpService.axiosClient.post('/org/owner', { username: username, organization: orgName })
          .then(function(response){
            setShowModal(false);
            setAlert({variant: "success", show: true, title: `User ${username} added as owner of ${orgName}`});
          })
          .catch((error) => {
            setShowModal(false);
            setAlert({variant: "danger", show: true, title: getErrorMessage(error)});
        });
    }

    let modal: JSX.Element | null = null;
    if(showModal){
        modal = (
            <Modal
            title={`Add ${username} as owner of ${orgName}?`}
            isOpen={showModal}
            variant={ModalVariant.small}
            aria-label="feedback modal"
            showClose={true}
            onClose={() => {setShowModal(false)}}
            aria-describedby="no-header-example"
            >
                <Button id="add-org-owner-confirm" variant="primary" onClick={addOwner}>Add Owner</Button>
            </Modal>
        );
    }
    return (<>
        <PageSection>
            <Card>
                {modal}
                <CardTitle className={"text-uppercase"}> Add Owner to Organization </CardTitle>
                {alert.show && <Alert id="add-org-owner-alert" isInline actionClose={<AlertActionCloseButton onClose={() => setAlert({ variant: 'success', show: false, title: ''})} />} variant={alert.variant} title={alert.title} />}
                <CardBody>
                    <Form id="add-org-owner-form">
                    <FormGroup label="Username" fieldId="add-org-owner-username" isRequired>
                        <TextInput
                        isRequired
                        type="text"
                        id="add-org-owner-username"
                        name="add-org-owner-username"
                        value={username}
                        onChange={(value) => setUsername(value)}
                        placeholder="Username"
                        />
                    </FormGroup>

                    <FormGroup label="Organization Name" fieldId="add-org-owner-orgname" isRequired>
                        <TextInput
                        isRequired
                        type="text"
                        id="add-org-owner-orgname"
                        name="add-org-owner-orgname"
                        value={orgName}
                        onChange={(value) => setOrgName(value)}
                        placeholder="Organization Name"
                        />
                    </FormGroup>

                    <ActionGroup>
                        <Button id="add-org-owner-submit" variant="primary" onClick={promptAddOwner}>Add Owner</Button>
                    </ActionGroup>
                    </Form>
                </CardBody>
            </Card>
        </PageSection>
    </>
    );
}
