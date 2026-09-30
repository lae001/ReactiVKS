import { render, screen } from '@testing-library/react';

import { MOCK_CONSENT_NOTICE } from '@/shared/mocks/data';

import { ConsentFieldset } from './ConsentFieldset';

describe('блок согласия', () => {
  it('без решения ни один вариант не выбран, выбор обязателен', () => {
    render(<ConsentFieldset notice={MOCK_CONSENT_NOTICE} value={null} onChange={() => {}} />);
    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(2);
    for (const r of radios) {
      expect(r).not.toBeChecked();
      expect(r).toBeRequired();
    }
  });
});
