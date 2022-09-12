import * as React from "react";
import {
  ActionGroup, Button, Card,
  CardBody,
  CardTitle, Form, FormGroup, Modal, ModalVariant,
  PageSection, TextInput, TextContent, TextListVariants,
  TextList, TextListItem, TextListItemVariants
} from '@patternfly/react-core';
import {useState} from "react";
import HttpService from "../../services/HttpService";

export const ExportCompliance: React.FunctionComponent = (props) => {
  const [userEmail, setUserEmail] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState(false);

  async function fetchUser() {
    if (userEmail != '') {
       HttpService.axiosClient.get(`/fetchuser/${userEmail}`)
      .then(function (response) {
        setResponse(response.data);
        console.log("response", response.data);
      })
      .catch(function (error) {
        setMessage(error.response.data.message);
        setIsModalOpen(true);
      });
    }
  }

  return (
    <PageSection>
      <Modal
        isOpen={isModalOpen}
        variant={ModalVariant.small}
        aria-label="feedback modal"
        showClose={true}
        aria-describedby="no-header-example"
        onClose={() => {
          setIsModalOpen(!isModalOpen);
        }}
      >
        <span>{message}</span>
      </Modal>
      <Card>
        <CardTitle className={'text-uppercase'}> Fetch User details </CardTitle>
        <CardBody>
          <Form>
            <FormGroup label="User email" fieldId="user-email" isRequired>
              <TextInput
                isRequired
                type="text"
                id="user-email"
                name="user-email"
                value={userEmail}
                onChange={(value) => setUserEmail(value)}
                placeholder="User email"
              />
            </FormGroup>

            { response ? (
              <TextContent>
                <TextList component={TextListVariants.dl}>
                  <TextListItem component={TextListItemVariants.dt}>Quay.io Username</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>
                    {response.username}
                  </TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Enabled</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>
                    {response.enabled ? 'True' : 'False'}
                  </TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Last Accessed</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>
                    {response.last_accessed}
                  </TextListItem>
                </TextList>
              </TextContent>) : null
            }

            <ActionGroup>
              <Button variant="primary" onClick={fetchUser}>
                Fetch User
              </Button>
            </ActionGroup>
          </Form>
        </CardBody>
      </Card>
    </PageSection>
  );
}
