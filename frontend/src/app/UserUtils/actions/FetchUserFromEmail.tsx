import * as React from "react";
import {
  ActionGroup, Button, Card,
  CardBody,
  CardTitle, Form, FormGroup, Modal, ModalVariant,
  PageSection, TextInput, TextContent, TextListVariants,
  TextList, TextListItem, TextListItemVariants
} from '@patternfly/react-core';
import {useState} from "react";
import HttpService from "src/services/HttpService";

export const FetchUserFromEmail: React.FunctionComponent = (props) => {
  const [userEmail, setUserEmail] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');

  const userEmailOnChange = (value) => {
    setUserEmail(value);
    if (value == '') {
      setResponse('');
    }
  }

  async function fetchUser() {
    if (userEmail != '') {
       HttpService.axiosClient.get(`/quayuseremail/${userEmail}`)
      .then(function (response) {
        setResponse(response.data);
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
        <CardTitle className={'text-uppercase'}> Fetch User details from users Quay.io Email </CardTitle>
        <CardBody>
          <Form>
            <FormGroup label="User email" fieldId="user-email" isRequired>
              <TextInput
                isRequired
                type="text"
                id="user-email"
                name="user-email"
                value={userEmail}
                onChange={(value) => userEmailOnChange(value)}
                placeholder="User email"
              />
            </FormGroup>

            { response ? (
              <TextContent>
                <TextList component={TextListVariants.dl}>
                  <TextListItem component={TextListItemVariants.dt}>Quay.io User name</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.username}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Enabled</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.enabled.toString()}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Is Paid User</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.paid_user.toString()}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Last Accessed</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.last_accessed}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Is Organization</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.is_organization.toString()}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Company</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.company}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Creation date</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.creation_date}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Last Accessed on</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.last_accessed}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Invoice Email</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.invoice_email}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Private Repositories count</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.private_repo_count}</TextListItem>

                  <TextListItem component={TextListItemVariants.dt}>Public Repositories count</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.public_repo_count}</TextListItem>
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
