import * as React from 'react';
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  Form,
  FormGroup,
  Modal,
  ModalVariant,
  PageSection,
  TextArea,
  FormSelect,
  ActionGroup, FormSelectOption,
  Banner, BannerProps,
  Split, SplitItem
} from '@patternfly/react-core';
import ReactMarkdown from 'react-markdown';
import { useState } from 'react';
import HttpService from "../../services/HttpService";

interface FormSelectEntry {
  value: string,
  label: string
}

const SiteUtils: React.FunctionComponent = (props) => {

  const availableMediaTypes: FormSelectEntry[] = [
    { value: "text/plan", label: "Text" },
    { value: "text/markdown", label: "Markdown" },
  ]

  const availableSeverityLevels: FormSelectEntry[] = [
    { value: "default", label: "default" },
    { value: "info", label: "info" },
    { value: "success", label: "success" },
    { value: "warning", label: "warning" },
    { value: "danger", label: "danger" },
  ]

  React.useEffect(() => {
    const banners = [];
    HttpService.axiosClient.get('banner')
    .then(function (response) {
      banners = response.data;
      setBanners(banners);
    })
    .catch(function (error) {
      console.log(error);
    });
  }, []);

  const [banners, setBanners] = React.useState({'banners': []});
  const [message, setMessage] = useState('');
  const [severity, setSeverity] = useState(availableSeverityLevels[0].value);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState('');
  const [openConfirmationModal, setOpenConfirmationModal] = useState(false);
  const [targetBannerId, setTargetBannerId] = useState(null);

  function resetBannerInput() {
    setTargetBannerId(null);
    setSeverity('');
    setMessage('');
  }

  async function onSaveBanner() {
    if (message && severity && !targetBannerId) {
       HttpService.axiosClient.post('/banner', {
        message,
        severity
      })
      .then(function (response) {
        setFeedbackMessage('Succeeded');
        setIsModalOpen(true);
        HttpService.axiosClient.get('/banner')
          .then(function (response) {
          setBanners(response.data);
        });
      })
      .catch(function (error) {
        setFeedbackMessage(error.response.data.message);
        setIsModalOpen(true);
      })
      .finally(() => {
        resetBannerInput();
      });
    }
    else if (message && severity && targetBannerId) {
      HttpService.axiosClient.put('/banner', {
        id: targetBannerId,
        message,
        severity
      })
      .then(function (response) {
        setFeedbackMessage('Succeeded');
        setIsModalOpen(true);
        HttpService.axiosClient.get('/banner').then(function (response) {
          setBanners(response.data);
        });
      })
      .catch(function (error) {
        setFeedbackMessage(error.response.data.message);
        setIsModalOpen(true);
      })
      .finally(() => {
        resetBannerInput();
      });
    }
  }

  function onClickDeleteButton(id) {
    setTargetBannerId(id);
    setOpenConfirmationModal(true);
  }

  function handleModalToggle() {
    setTargetBannerId(null);
    setOpenConfirmationModal(false);
  }

  async function onDeleteBanner(id) {
    handleModalToggle();
    HttpService.axiosClient.delete(`/banner/${id}`)
    .then(function (response) {
      setFeedbackMessage('Succeeded');
      setIsModalOpen(true);
      HttpService.axiosClient.get('/banner').then(function (response) {
        setBanners(response.data);
      });
    })
    .catch(function (error) {
      setFeedbackMessage(error.response.data.message);
      setIsModalOpen(true);
    });
  }

  function onEditBanner(banner) {
    setMessage(banner.content);
    setSeverity(banner.severity);
    setTargetBannerId(banner.id);
  }

  return(
    <PageSection>
      <Modal
          isOpen={isModalOpen}
          variant={ModalVariant.small}
          aria-label="feedback modal"
          showClose={true}
          aria-describedby="no-header-example"
          onClose={() => { setIsModalOpen(!isModalOpen)} }
        >{feedbackMessage}</Modal>
      <Card>
        <CardTitle className={"text-uppercase"}> Update Site Banner </CardTitle>
        <CardBody>
          <Form>
            <FormGroup label="Name" fieldId="banner-update" isRequired>
              <TextArea
                isRequired
                type="text"
                id="simple-form-name"
                name="simple-form-name"
                aria-describedby="simple-form-name-helper"
                value={message}
                onChange={(value) => setMessage(value)}
                placeholder="Enter new message"
                rows={4}
              />
            </FormGroup>

            <FormGroup label="Severity" fieldId="severity">
              <FormSelect
                id="severity"
                name="severity"
                aria-label="Message Severity"
                value={severity}
                onChange={(value) => setSeverity(value)}
              >
                {availableSeverityLevels.map((s, index) => (
                  <FormSelectOption key={index} value={s.value} label={s.label} />
                ))}
              </FormSelect>
            </FormGroup>

            {message && message.length > 0 &&
              <FormGroup label="Preview" fieldId="preview">
                <Banner variant={severity as BannerProps["variant"]}>
                  <ReactMarkdown>{message}</ReactMarkdown>
                </Banner>
              </FormGroup>
            }

            <ActionGroup>
              <Button variant="primary" onClick={onSaveBanner}>Save</Button>
            </ActionGroup>
          </Form>

        </CardBody>
      </Card>

      {banners.length > 0 && banners.map((banner) => (
        <Card>
          <CardTitle className={"text-uppercase"}> Banner </CardTitle>
          <CardBody>
            <Split hasGutter>
              <SplitItem isFilled>
                <Banner variant={banner.severity as BannerProps["variant"]}>
                  <ReactMarkdown>{banner.content}</ReactMarkdown>
                </Banner>
              </SplitItem>
              <SplitItem>
                <Button variant="secondary" onClick={() => onEditBanner(banner)}>edit</Button>
              </SplitItem>
              <SplitItem>
                <Button variant="danger" onClick={() => onClickDeleteButton(banner.id)}>delete</Button>
              </SplitItem>
            </Split>
          </CardBody>
        </Card>
      ))}

      {openConfirmationModal && <Modal
          variant={ModalVariant.small}
          title=""
          isOpen={openConfirmationModal}
          onClose={handleModalToggle}
          actions={[
            <Button key="confirm" variant="primary" onClick={() => onDeleteBanner(targetBannerId)}>
              Confirm
            </Button>,
            <Button key="cancel" variant="link" onClick={handleModalToggle}>
              Cancel
            </Button>
          ]}
        >
          Are you sure you want to delete this banner?
        </Modal>}
    </PageSection>
  )
}

export { SiteUtils };
