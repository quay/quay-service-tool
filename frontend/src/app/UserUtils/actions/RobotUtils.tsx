import {
  ActionGroup, Alert, AlertActionCloseButton, Button,
  Card,
  CardBody,
  CardTitle, DescriptionList, DescriptionListDescription, DescriptionListGroup, DescriptionListTerm,
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

export const CreateRobotToken: React.FunctionComponent = () => {
  const [robotName, setRobotName] = useState('');
  const [orgName, setOrgName] = useState('');
  const [token, setToken] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [alert, setAlert] = useState<AlertType>({
    variant: 'success',
    show: false,
    title: ''
  });


  async function createRobotToken(){
    HttpService.axiosClient.post(`/robot/token`, {robot_name: robotName, organization: orgName, token: token})
      .then(function(response){
        setShowModal(false);
        setAlert({variant: "success", show: true, title: `Robot ${response.data.robot_name} created`});
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
        title={'Create Robot token'}
        isOpen={showModal}
        variant={ModalVariant.small}
        aria-label="feedback modal"
        showClose={true}
        onClose={() => {setShowModal(false)}}
        aria-describedby="no-header-example"
        actions={[
          (<Button key='create' id="create-robot-token-confirm" variant="primary" onClick={createRobotToken}>
            Create Robot Token
          </Button>)
        ]}
      >
        <DescriptionList  className={'pf-u-pb-lg'}>
          <DescriptionListGroup>
            <DescriptionListTerm>Robot Name</DescriptionListTerm>
            <DescriptionListDescription>{robotName}</DescriptionListDescription>
          </DescriptionListGroup>
          <DescriptionListGroup>
            <DescriptionListTerm>Organization</DescriptionListTerm>
            <DescriptionListDescription>{orgName}</DescriptionListDescription>
          </DescriptionListGroup>
        </DescriptionList>
      </Modal>
    );
  }

  return (<>
    <PageSection>
      <Card>
        {modal}
        <CardTitle className={"text-uppercase"}> Create Robot Token </CardTitle>
        {alert.show && <Alert id="create-robot-token-alert" isInline actionClose={<AlertActionCloseButton onClose={() => setAlert({ variant: 'success', show: false, title: '' })} />} variant={alert.variant} title={alert.title} />}
        <CardBody>
          <Form id="create-robot-token-form">
            <FormGroup label="Robot name" fieldId="create-robot-token-username" isRequired>
              <TextInput
                isRequired
                type="text"
                id="create-robot-token-username"
                name="create-robot-token-username"
                value={robotName}
                onChange={(value) => setRobotName(value)}
                placeholder="Robot name"
              />
            </FormGroup>

            <FormGroup label="Organization Name" fieldId="create-robot-token-org" isRequired>
              <TextInput
                isRequired
                type="text"
                id="create-robot-token-org"
                name="create-robot-token-org"
                value={orgName}
                onChange={(value) => setOrgName(value)}
                placeholder="Organization Name"
              />
            </FormGroup>

            <FormGroup label="Token" fieldId="create-robot-token-token" isRequired>
              <TextInput
                isRequired
                type="text"
                id="create-robot-token-token"
                name="create-robot-token-token"
                value={token}
                onChange={(value) => setToken(value)}
                placeholder="Token"
              />
            </FormGroup>

            <ActionGroup>
              <Button id="create-robot-token-submit" variant="primary" onClick={() => setShowModal(true)}>Create Token</Button>
            </ActionGroup>
          </Form>
        </CardBody>
      </Card>
    </PageSection>
  </>
  );
}
