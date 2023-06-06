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

export const FetchUserFromName: React.FunctionComponent = (props) => {
  const [userName, setUserName] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');

  const userNameOnChange = (value) => {
    setUserName(value);
    if (value == '') {
      setResponse('');
    }
  }

  async function fetchUser() {
    if (userName != '') {
       HttpService.axiosClient.get(`/quayusername/${userName}`)
      .then(function (response) {
        setResponse(response.data);
      })
      .catch(function (error) {
        error.response ? setMessage(error?.response?.data?.message) : setMessage(error);
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
        <CardTitle className={'text-uppercase'}> Fetch User details from users Quay.io Username </CardTitle>
        <CardBody>
          <Form>
            <FormGroup label="User name" fieldId="user-name" isRequired>
              <TextInput
                isRequired
                type="text"
                id="user-name"
                name="user-name"
                value={userName}
                onChange={(value) => userNameOnChange(value)}
                placeholder="User name"
              />
            </FormGroup>

            { response ? (
              <TextContent>
                <TextList component={TextListVariants.dl}>
                  <TextListItem component={TextListItemVariants.dt}>User account number</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.account_number}</TextListItem>
                  <TextListItem component={TextListItemVariants.dt}>User email</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.email}</TextListItem>

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

                  <TextListItem component={TextListItemVariants.dt}>Stripe ID</TextListItem>
                  <TextListItem component={TextListItemVariants.dd}>{response.stripe_id}</TextListItem>

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
