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
  List,
  ListItem,
  Spinner,
  ActionGroup, FormSelectOption,
  Banner, BannerProps,
  Split, SplitItem, Alert
} from '@patternfly/react-core';
import ReactMarkdown from 'react-markdown';
import { useState, useEffect } from 'react';
import HttpService from "src/services/HttpService";
import UserService from "src/services/UserService";

type FormSelectEntry = {
  value: string,
  label: string
}

type banner = {
    id: number,
    content: string,
    uuid: string,
    severity: string,
    mediatype: {
      id: number,
      name: string,
    }
}

const availableSeverityLevels: FormSelectEntry[] = [
  { value: "default", label: "default" },
  { value: "info", label: "info" },
  { value: "success", label: "success" },
  { value: "warning", label: "warning" },
  { value: "danger", label: "danger" },
]

const ADMIN_ROLE = window.ADMIN_ROLE || process.env.ADMIN_ROLE;

export const SiteUtils: React.FunctionComponent = (props) => {

  const [banners, setBanners] = useState<banner[]>([]);
  const [message, setMessage] = useState('');
  const [severity, setSeverity] = useState(availableSeverityLevels[0].value);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState('');
  const [openConfirmationModal, setOpenConfirmationModal] = useState(false);
  const [targetBannerId, setTargetBannerId] = useState(null);
  const [bannerLoading, setBannerLoading] = useState(true);
  const [bannerLoadFailure, setBannerLoadFailure] = useState(false);

  useEffect(() => {
    if (UserService.hasRealmRole(ADMIN_ROLE)) {
      loadBanners();
    }
  }, []);

  function resetBannerInput() {
    setTargetBannerId(null);
    setSeverity(availableSeverityLevels[0].value);
    setMessage('');
  }

  async function loadBanners(){
    setBannerLoading(true);
    HttpService.axiosClient.get('banner')
      .then(function (response) {
        setBannerLoadFailure(false);
        setBanners(response.data.messages);
        setBannerLoading(false);
      })
      .catch(function (error) {
        setBannerLoadFailure(true);
        setBannerLoading(false);
      })
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
        loadBanners()
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
        loadBanners()
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
      loadBanners()
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

  // Populate banner list depending on current state
  let bannerBody: React.ReactElement | React.ReactElement[] | null = null
  if (bannerLoading) {
    bannerBody = (<Spinner role="loading-banners-icon" isSVG />)
  } else if (bannerLoadFailure) {
    bannerBody = (<Alert id="enable-user-alert" isInline title='Failed to load banners' variant='danger'/>)
  } else if (banners.length > 0){
    bannerBody = banners.map((banner) => (
        <ListItem key={banner.uuid}>
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
        </ListItem>
      ))
  } else {
    bannerBody = (<div id="no-banners-found-message">No existing banners</div>)
  }

  return (
    ( UserService.hasRealmRole(ADMIN_ROLE) ?
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
        <CardTitle className={"text-uppercase"}> Add Site Banner </CardTitle>
        <CardBody>
          <Form>
            <FormGroup label="Name" fieldId="banner-update" isRequired>
              <TextArea
                isRequired
                type="text"
                id="message-form"
                name="message-form"
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

        <Card>
          <CardTitle className={"text-uppercase"}> Existing Banners </CardTitle>
          <CardBody>
            <List isPlain isBordered>
              {bannerBody}
            </List>
          </CardBody>
        </Card>

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
    </PageSection> : null)
  )
}
