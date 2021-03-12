import * as React from 'react';
import { storiesOf } from '@storybook/react';
import { withInfo } from '@storybook/addon-info';
import { SiteUtils } from '@app/SiteUtils/SiteUtils';

const stories = storiesOf('Components', module);
stories.addDecorator(withInfo);
stories.add(
  'SiteUtils',
  () => <SiteUtils />,
  { info: { inline: true } }
);
