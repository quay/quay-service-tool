import * as React from "react";
import {useState} from "react";
import {
  ActionGroup, Button,
  Card,
  CardBody,
  CardTitle,
  Form,
  FormGroup,
  Modal,
  ModalVariant,
  PageSection,
  TextInput
} from "@patternfly/react-core";
import {UserInfo} from "@app/common/UserInfo";
import HttpService from "src/services/HttpService";

export const FetchUserFromStripeID: React.FunctionComponent = (props) => {
  const [stripeId, setStripeId] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');

  const stripeIdOnChange = (value) => {
    setStripeId(value);
    if (value == '') {
      setResponse('');
    }
  }

  async function fetchUser() {
    if (stripeId != '') {
       HttpService.axiosClient.get(`/user/stripe/${stripeId}`)
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
        <CardTitle className={'text-uppercase'}> Fetch User details from users Stripe ID </CardTitle>
        <CardBody>
          <Form>
            <FormGroup label="Stripe ID" fieldId="stripe-id" isRequired>
              <TextInput
                isRequired
                type="text"
                id="stripe-id"
                name="stripe-id"
                value={stripeId}
                onChange={(value) => stripeIdOnChange(value)}
                placeholder="Stripe ID"
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
  );
}
