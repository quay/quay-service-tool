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
import { DisableUser } from "src/app/UserUtils/actions/DisableUser";
import { EnableUser } from "src/app/UserUtils/actions/EnableUser";
import {UserInfo} from "@app/common/UserInfo";

export const ExportCompliance: React.FunctionComponent = (props) => {
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
       HttpService.axiosClient.get(`/federateduser/${userName}`)
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
    <div>
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
              <FormGroup label="User name" fieldId="user-name" isRequired>
                <TextInput
                  isRequired
                  type="text"
                  id="user-name"
                  name="user-name"
                  value={userName}
                  onChange={(value) => userNameOnChange(value)}
                  placeholder="Red Hat Account Name"
                />
              </FormGroup>

              { response ? <UserInfo userinfo={response} /> : null }

              <ActionGroup>
                <Button variant="primary" onClick={fetchUser}>
                  Fetch User
                </Button>
              </ActionGroup>
            </Form>
          </CardBody>
        </Card>
      </PageSection>
      <DisableUser></DisableUser>
      <EnableUser></EnableUser>
    </div>
  );
}
