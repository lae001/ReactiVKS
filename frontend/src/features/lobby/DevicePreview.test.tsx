import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useLocalMedia } from '@/shared/hooks/use-local-media';
import { loadDevicePrefs } from '@/shared/lib/device-prefs';
import { installFakeMediaDevices, removeSinkIdSupport, stubSinkIdSupport } from '@/test/fake-media';

import { DevicePreview } from './DevicePreview';

function Preview() {
  const media = useLocalMedia();
  return <DevicePreview media={media} displayName="" />;
}

afterEach(() => {
  vi.unstubAllGlobals();
  removeSinkIdSupport();
});

describe('превью и выбор устройств в лобби', () => {
  it('показывает списки камер, микрофонов и динамиков и сохраняет выбор', async () => {
    stubSinkIdSupport();
    installFakeMediaDevices();
    const user = userEvent.setup();
    render(<Preview />);

    const camera = await screen.findByRole('combobox', { name: 'Камера' });
    await waitFor(() => expect(within(camera).getAllByRole('option')).toHaveLength(2));
    expect(
      within(screen.getByRole('combobox', { name: 'Микрофон' })).getAllByRole('option'),
    ).toHaveLength(2);
    const speaker = screen.getByRole('combobox', { name: 'Динамик' });
    expect(within(speaker).getByRole('option', { name: 'Наушники' })).toBeInTheDocument();

    await user.selectOptions(camera, 'Камера USB');
    await user.selectOptions(speaker, 'Наушники');
    expect(loadDevicePrefs()).toEqual({ cameraId: 'cam-b', speakerId: 'spk-b' });
    expect(screen.getByRole('button', { name: /Проверить звук/ })).toBeInTheDocument();
  });

  it('в браузере без setSinkId выбор динамика скрыт, вместо него пояснение', async () => {
    installFakeMediaDevices();
    render(<Preview />);
    await screen.findByRole('combobox', { name: 'Камера' });
    expect(screen.queryByRole('combobox', { name: 'Динамик' })).not.toBeInTheDocument();
    expect(screen.getByText(/Выбрать динамик можно только в Chrome и Edge/)).toBeInTheDocument();
  });

  it('есть индикатор уровня микрофона', async () => {
    installFakeMediaDevices();
    render(<Preview />);
    const meter = await screen.findByRole('meter', { name: 'Уровень микрофона' });
    expect(meter).toHaveAttribute('aria-valuenow', '0');
  });

  it('доступ к камере запрещен – сообщение по-русски и «Повторить», микрофон выбирается', async () => {
    installFakeMediaDevices({ fail: { video: 'NotAllowedError' } });
    render(<Preview />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Браузер не дал доступ к камере');
    expect(within(alert).getByRole('button', { name: 'Повторить' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Камера' })).toBeDisabled();
    expect(await screen.findByRole('combobox', { name: 'Микрофон' })).toBeEnabled();
    expect(screen.getByText('Камера недоступна')).toBeInTheDocument();
  });

  it('устройств нет – сообщение об отсутствии и пустые списки', async () => {
    installFakeMediaDevices({ devices: [] });
    render(<Preview />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Камера не найдена');
    expect(alert).toHaveTextContent('Микрофон не найден');
    expect(screen.getByRole('combobox', { name: 'Камера' })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: 'Микрофон' })).toBeDisabled();
  });
});
