import { TextDecoder, TextEncoder } from 'util';
import { configure } from 'enzyme';
import ReactEighteenAdapter from '@cfaester/enzyme-adapter-react-18';

Object.assign(global, { TextDecoder, TextEncoder });
configure({ adapter: new ReactEighteenAdapter() });
