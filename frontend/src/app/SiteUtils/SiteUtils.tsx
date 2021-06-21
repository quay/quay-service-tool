import * as React from 'react';
import {
  Button,
  Card,
  CardBody,
  CardTitle,
  Form,
  FormGroup,
  PageSection,
  TextArea,
  FormSelect,
  ActionGroup, FormSelectOption,
  Banner, BannerProps, Label
} from '@patternfly/react-core';
import ReactMarkdown from 'react-markdown';
import { useState } from 'react';

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

  const [banners, setBanners] = useState(props['banners']);
  const [message, setMessage] = useState('');
  const [mediaType, setMediaType] = useState('');
  const [severity, setSeverity] = useState('');

  return(
    <PageSection>
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

            {message.length > 0 &&
              <FormGroup label="Preview" fieldId="preview">
                <Banner variant={severity as BannerProps["variant"]}>
                  <ReactMarkdown>{message}</ReactMarkdown>
                </Banner>
              </FormGroup>
            }

            <ActionGroup>
              <Button variant="primary">Update Banner</Button>
              <Button variant="danger">Clear Banner</Button>
            </ActionGroup>
          </Form>


        </CardBody>
      </Card>
    </PageSection>
  )
}

export { SiteUtils };
